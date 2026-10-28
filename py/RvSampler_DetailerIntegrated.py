# Pipe-based detection, optional SAM2/matting and diffusion detailing.
import json
from functools import partial

import torch
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.common import get_workflow_node
from ..core.detailer_color_match import match_detail_crop
from ..core.detailer_conditioning import DetailerConditioning
from ..core.detailer_configuration import NODE_ID, PROFILE
from ..core.detailer_execution import detail_images
from ..core.detailer_models import model_fingerprint
from ..core.detailer_pipe import SAMPLING_FIELDS, basic_pipe, read_pipe
from ..core.detailer_regions import (
    combined_mask,
    detect_regions,
    detection_source,
    refine_regions,
)
from ..core.detailer_review import DetailerReview
from ..core.image_helpers import flatten_images, unwrap_value
from ..core.sampler_configuration import (
    WIDGET_TYPE,
    default_configuration,
    detailer_editor_spec,
    editor_spec,
    resolve_seed,
    validate_configuration,
)
from ..core.seed_cache import automatic_fingerprint, record_automatic_execution


class RvSampler_DetailerIntegrated(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=NODE_ID, display_name='Detailer (Advanced)',
            category=CATEGORY.MAIN.value + CATEGORY.SAMPLER.value,
            description='Use external detections from the PIPE or a local YOLO model, automatically detecting boxes or segmentation from its checkpoint. Optionally refine with SAM2 and matting before diffusion detailing. Detection models are released before sampling. IO Detailer and IO KSampler pipes are supported.',
            is_input_list=True, is_output_node=True,
            inputs=[
                io.Image.Input('image', tooltip='Original images, as a batch or list. Do not use an image with drawn detection boxes.'),
                io.Custom('PIPE').Input('pipe', tooltip='Model, VAE, conditioning and optional CLIP/detections from IO Detailer or IO KSampler. Non-None external SEGS/BBOXES bypass internal YOLO. Use pipe settings enables sampler, scheduler, steps, CFG, denoise (one value or category list) and seed overrides.'),
                io.String.Input('configuration', socketless=True, default=json.dumps(default_configuration(PROFILE)),
                                extra_dict={'widgetType': WIDGET_TYPE, 'editorSpec': editor_spec(PROFILE)}),
            ],
            outputs=[io.Image.Output('image', is_output_list=True), io.Custom('PIPE').Output('pipe')],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo, io.Hidden.unique_id],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(unwrap_value(configuration), PROFILE)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **inputs):
        raw = unwrap_value(configuration)
        config = validate_configuration(raw, PROFILE)
        pipe = unwrap_value(inputs.get('pipe'))
        pipe_seed = config['parameters']['allow_overwrite'] and isinstance(pipe, dict) and pipe.get('seed') is not None
        seed_state = automatic_fingerprint() if config['seed']['policy'] == 'random' and not pipe_seed else raw
        # Some ComfyUI caches only recognize V1's bare "UNIQUE_ID" hidden
        # type, not V3's tuple form. Keep review results owned by this node even
        # when another detailer has identical settings and upstream inputs.
        return cls.hidden.unique_id, seed_state, model_fingerprint(config['parameters'])

    @classmethod
    def execute(cls, image, pipe, configuration):
        config = validate_configuration(unwrap_value(configuration), PROFILE)
        context = read_pipe(pipe)
        source = detection_source(bboxes=context.get('bboxes'), segs=context.get('segs'))
        resources = basic_pipe(context)
        conditioning = DetailerConditioning(context, source, context.get('detection', config['parameters']['detection']),
            denoise=context.get('denoise') if config['parameters']['allow_overwrite'] else None)
        local_seed = dict(config['seed'])
        pipe_seed = False
        if context.get('detection') is not None:
            config['parameters']['detection'] = context['detection']
        if config['parameters']['allow_overwrite']:
            for key in SAMPLING_FIELDS:
                if key != 'denoise' and context.get(key) is not None:
                    config['parameters'][key] = context[key]
            if conditioning.denoises:
                # Keep the panel configuration scalar. Each category receives
                # its own resolved denoise at the sampling boundary below.
                config['parameters']['denoise'] = conditioning.denoises[0]
            if context.get('seed') is not None:
                if type(context['seed']) is not int or not 0 <= context['seed'] <= 2**64 - 1:
                    raise ValueError('Pipe seed must be an unsigned 64-bit integer.')
                config['seed'] = {'value': str(context['seed']), 'policy': 'fixed'}
                pipe_seed = True
        config = validate_configuration(json.dumps(config), PROFILE)
        frames = flatten_images(image)
        if not frames or any(frame.ndim != 4 or frame.shape[-1] not in (3, 4) for frame in frames):
            raise ValueError('Detailer requires RGB or RGBA images.')
        parameters = config['parameters']
        review = DetailerReview(frames, parameters, cls.hidden, bboxes=context.get('bboxes'), segs=context.get('segs'),
                               group_by_label=conditioning.group_by_label)
        detected = review.stage('detection', lambda: detect_regions(frames, parameters,
            bboxes=context.get('bboxes'), segs=context.get('segs')))
        conditioning.validate_regions(detected)
        prepared = review.stage('segmentation', lambda: refine_regions(frames, detected, parameters,
                                group_by_label=conditioning.group_by_label))
        # Reviewing regions must not consume a local random/increment seed.
        seed = resolve_seed(config['seed'])
        sampling = {key: config['parameters'][key] for key in detailer_editor_spec()['fields']
                    if key not in ('allow_overwrite', 'live_preview')}
        crop_postprocess = partial(match_detail_crop, method=parameters['color_match_method'], strength=parameters['color_match_strength']) \
            if parameters['color_match_enabled'] and parameters['color_match_strength'] > 0 else None
        enhanced, detailed, masks = [], [], []
        for frame, regions in zip(frames, prepared, strict=True):
            masks.append(combined_mask(regions))
            if not regions[1]:
                enhanced.append(frame)
                detailed.append(regions)
                continue
            current, sampled, offset = frame, [], 0
            for group in conditioning.groups(regions):
                label = group[1][0].label
                positive, negative = conditioning.conditioning(label)
                group_resources = (*resources[:3], positive, negative)
                group_sampling = {**sampling, 'denoise': conditioning.denoise(label, sampling['denoise'])}
                result, segments, _pipes = detail_images([current], group, group_resources,
                    seed=(seed + offset) % (2**64), live_preview=False, crop_postprocess=crop_postprocess, **group_sampling)
                current = result[0]
                sampled.extend(seg for _shape, items in segments for seg in items)
                offset += len(group[1])
            enhanced.append(current)
            detailed.append((regions[0], sampled))
        extra = cls.hidden.extra_pnginfo
        saved = get_workflow_node(extra, str(cls.hidden.unique_id)) if extra and cls.hidden.unique_id is not None else None
        if saved is not None:
            saved['widgets_values'] = [json.dumps({**config, 'seed': {'value': str(seed), 'policy': 'fixed'}})]
        ui = {**review.ui, 'images': [], 'eclipse_seed': [str(seed)]}
        if (parameters['allow_overwrite'] or review.pending) and not pipe_seed:
            ui['eclipse_local_seed'] = [local_seed]
        record_automatic_execution(not pipe_seed and config['seed']['policy'] == 'random')
        # Preserve initial generation metadata. Record the actual enhancement
        # separately, and never let a stale upstream latent shadow these images.
        context.pop('latent', None)
        pipe_images = torch.cat(enhanced) if all(frame.shape[1:] == enhanced[0].shape[1:] for frame in enhanced) else enhanced
        settings = {**config['parameters'], 'seed': seed}
        if len(conditioning.denoises) > 1:
            settings['denoise'] = list(conditioning.denoises)
        context.update(image=pipe_images, segs=detailed, mask=masks, detailer_settings=settings)
        review.finish()
        return io.NodeOutput(enhanced, context, ui=ui)
