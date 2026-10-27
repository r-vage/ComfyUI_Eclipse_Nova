# Intermediate review stops must not cache an unfinished detailer node output.
# Only bounded CPU masks and preview references survive a review interruption;
# models, source images, conditioning and ControlNet hooks are never retained.
import hashlib
import json
import threading
from collections import OrderedDict
from pathlib import Path

import folder_paths
import nodes
import numpy as np
import torch
from comfy.model_management import InterruptProcessingException
from comfy_execution.utils import get_executing_context
from PIL import Image, ImageDraw
from server import PromptServer

from ..extern.impact.core import SEG
from .detailer_models import model_fingerprint
from .detailer_regions import combined_mask, detection_source
from .image_helpers import pil2tensor, tensor2pil
from .seg_masks import MetadataWrapper

_DETECTION_FIELDS = ('yolo_model', 'detection',
    'detection_device', 'threshold', 'nms_iou', 'bbox_dilation', 'crop_factor', 'drop_size',
    'selection', 'sort_by', 'descending', 'take_start', 'take_count', 'box_selection', 'box_indices')
_REFINEMENT_FIELDS = ('sam2_enabled', 'sam2_model', 'refine_edges', 'detection_device', 'precision',
    'detail_method', 'detail_erode', 'detail_dilate', 'black_point', 'white_point', 'max_megapixels',
    'mask_grow', 'mask_blur', 'invert_mask', 'combined', 'bbox_fill', 'contour_fill', 'crop_factor', 'drop_size')


def _digest(*values):
    digest = hashlib.sha256()

    def add(value):
        if isinstance(value, torch.Tensor):
            value = value.detach().cpu().contiguous().numpy()
        if isinstance(value, np.ndarray):
            add((str(value.dtype), value.shape))
            digest.update(memoryview(np.ascontiguousarray(value)).cast('B'))
        elif isinstance(value, MetadataWrapper):
            add((value.batch_index, value.original_wrapper))
        elif isinstance(value, dict):
            add(sorted(value.items()))
        elif isinstance(value, (list, tuple)):
            digest.update(b'[')
            for item in value:
                add(item)
            digest.update(b']')
        elif value is None or isinstance(value, (str, int, float, bool, np.number)):
            digest.update(json.dumps(value.item() if isinstance(value, np.number) else value).encode())
            digest.update(b'\0')
        else:
            # Hook identity affects ownership, but the hook itself is not kept.
            add((type(value).__module__, type(value).__qualname__, id(value)))

    for value in values:
        add(value)
    return digest.hexdigest()


def _pack(regions, limit):
    packed, size = [], 0
    for shape, segments in regions:
        items = []
        for seg in segments:
            hook = getattr(seg.control_net_wrapper, 'original_wrapper', seg.control_net_wrapper)
            if hook is not None or seg.cropped_image is not None:
                return None, 0
            mask = seg.cropped_mask
            if isinstance(mask, torch.Tensor):
                mask = mask.detach().cpu().numpy()
            mask = np.asarray(mask, dtype=np.float32)
            size += mask.nbytes
            if size > limit:
                return None, 0
            items.append((mask.copy(), float(seg.confidence), tuple(seg.crop_region), tuple(seg.bbox), str(seg.label)))
        packed.append((tuple(shape), items))
    return packed, size


def _unpack(packed):
    return [(shape, [SEG(None, mask.copy(), confidence, crop, bbox, label, MetadataWrapper(None, 0))
                    for mask, confidence, crop, bbox, label in items]) for shape, items in packed]


class ReviewCache:
    def __init__(self, max_entries=64, max_bytes=64 * 1024 * 1024):
        self.entries = OrderedDict()
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self.lock = threading.RLock()

    def entry(self, key, signature):
        with self.lock:
            value = self.entries.get(key)
            if value is None or value['signature'] != signature:
                value = self.entries[key] = {'signature': signature, 'reviewed': False, 'packed': None, 'size': 0, 'images': []}
            self.entries.move_to_end(key)
            while len(self.entries) > self.max_entries:
                self.entries.popitem(last=False)
            return value

    def retain(self, entry, regions):
        packed, size = _pack(regions, self.max_bytes)
        with self.lock:
            if size <= self.max_bytes:
                entry.update(packed=packed, size=size)
            # Retain tiny review markers even if their mask data is evicted.
            total = sum(item['size'] for item in self.entries.values())
            for item in self.entries.values():
                if total <= self.max_bytes:
                    break
                total -= item['size']
                item.update(packed=None, size=0)


_cache = ReviewCache()


def preview_images(frames, regions, stage):
    previews = []
    for frame, region in zip(frames, regions, strict=True):
        image = tensor2pil(frame[..., :3])
        width, height = image.size
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        if stage == 'segmentation':
            mask = Image.fromarray(combined_mask(region)[0].numpy()).resize(image.size, Image.Resampling.BILINEAR)
            alpha = np.asarray(mask)[..., None] * .5
            pixels = np.asarray(image).astype(np.float32)
            image = Image.fromarray((pixels * (1 - alpha) + np.array([40, 220, 155]) * alpha).round().astype(np.uint8))
        else:
            draw = ImageDraw.Draw(image)
            for seg in region[1]:
                x1, y1, x2, y2 = seg.bbox
                box = (x1 * image.width / width, y1 * image.height / height,
                       x2 * image.width / width, y2 * image.height / height)
                draw.rectangle(box, outline=(40, 220, 155), width=3)
                label = f'{seg.label} {float(seg.confidence):.0%}'
                draw.text((box[0] + 3, max(0, box[1] - 17)), label, fill='white', stroke_width=1, stroke_fill='black')
        previews.append(pil2tensor(image)[0])
    return nodes.PreviewImage().save_images(images=previews)['ui']['images']


def _previews_exist(images):
    root = Path(folder_paths.get_temp_directory())
    return bool(images) and all((root / item.get('subfolder', '') / item['filename']).is_file() for item in images)


class DetailerReview:
    def __init__(self, frames, parameters, hidden, *, bboxes=None, segs=None, group_by_label=False):
        self.frames, self.parameters = frames, parameters
        self.server = getattr(PromptServer, 'instance', None)
        self.client = getattr(self.server, 'client_id', None)
        self.node_id = str(hidden.unique_id)
        workflow = (hidden.extra_pnginfo or {}).get('workflow', {})
        self.workflow_id = workflow.get('id')
        self.scope = (self.client, self.workflow_id, self.node_id)
        self.pending = parameters['stop_detection'] or parameters['stop_segmentation']
        source = detection_source(bboxes=bboxes, segs=segs)
        external = segs if source == 'SEGS' else bboxes if source == 'BBOXES' else None
        self.detection_key = _digest(frames, source, external,
            {key: parameters[key] for key in _DETECTION_FIELDS},
            model_fingerprint(parameters, refinement=False) if source == 'YOLO' else ())
        self.keys = {'detection': self.detection_key, 'segmentation': _digest(self.detection_key,
            {key: parameters[key] for key in _REFINEMENT_FIELDS}, group_by_label, model_fingerprint(parameters, detection=False))}
        self.ui, self.entries = {}, []

    def stage(self, stage, produce):
        entry = _cache.entry((*self.scope, stage), self.keys[stage])
        self.entries.append(entry)
        with _cache.lock:
            packed = entry['packed']
        regions = _unpack(packed) if packed is not None else produce()
        if self.pending and packed is None:
            _cache.retain(entry, regions)
        if not _previews_exist(entry['images']):
            entry['images'] = preview_images(self.frames, regions, stage)
        stop = self.parameters['stop_' + stage]
        paused = stop and not entry['reviewed']
        ui = {'eclipse_detailer_' + stage: entry['images'],
              'eclipse_detailer_' + stage + '_status': [{'counts': [len(item[1]) for item in regions], 'paused': paused}]}
        if paused and stage == 'detection':
            ui.update(eclipse_detailer_segmentation=[], eclipse_detailer_segmentation_status=[])
        self.ui.update(ui)
        context = get_executing_context()
        if self.server is not None and self.client is not None:
            self.server.send_sync('eclipse-nova-detailer-review', {
                'node_id': self.node_id, 'workflow_id': self.workflow_id,
                'prompt_id': getattr(context, 'prompt_id', None), 'output': ui,
            }, self.client)
        entry['reviewed'] = bool(stop)
        if paused:
            # Returning partial outputs would make ComfyUI cache an unfinished
            # node. Interrupt before returning, then resume via the review key.
            raise InterruptProcessingException()
        return regions

    def finish(self):
        with _cache.lock:
            for entry in self.entries:
                entry.update(packed=None, size=0)
