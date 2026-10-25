# Two-stage latent sampling; decoding remains owned by the shared sampler engine.
import comfy.sample
import comfy.samplers
import comfy.utils
import torch

from .detail_daemon import wrap_detail
from .sampler_extras import prepare_extras, qwen_sigmas
from .sampler_preview import prepare_callback


def second_stage_denoise(parameters):
    return parameters['second_denoise'] if parameters['second_start'] == 0 else 1.0


def sample_stages(*, parameters, model, samples, seed, steps, cfg, sampler_name,
                  scheduler, denoise, batch_index, noise_mask, preview_mode, positive, negative, model_2=None):
    primary_model = model
    use_second = parameters['two_stage'] and model_2 is not None and model_2 is not model
    if use_second:
        validate_model_pair(model, model_2)
    model = prepare_extras(parameters, primary_model)
    if not parameters['two_stage'] and denoise <= 0:
        return samples
    stages = [{'steps': steps, 'cfg': cfg, 'sampler_name': sampler_name, 'scheduler': scheduler,
               'start': parameters['start_step'], 'end': parameters['end_step'],
               'add_noise': parameters['add_noise'], 'leftover': parameters['leftover_noise']}]
    if parameters['two_stage']:
        stages.append({key: parameters['second_' + key] for key in
                       ('steps', 'cfg', 'sampler_name', 'scheduler', 'start', 'end', 'add_noise', 'leftover')})
    # Reuse one preview decoder across stages instead of keeping two during replacement.
    callback = prepare_callback(model, steps) if preview_mode != 'None' else None
    for index, stage in enumerate(stages):
        if index and use_second:
            # Drop the previous preview decoder before constructing one for the
            # next device/model. ComfyUI manages model offloading during sampling.
            callback = None
            model = prepare_extras(parameters, model_2)
            callback = prepare_callback(model, stage['steps']) if preview_mode != 'None' else None
        if index and parameters['latent_upscale']:
            # Krea2/Qwen Image use a single-frame Wan latent even for still images.
            # ComfyUI's spatial upscale preserves that frame axis and the batch.
            if samples.is_nested or not (samples.ndim == 4 or (samples.ndim == 5 and samples.shape[2] == 1)):
                raise ValueError('Between-stage latent upscale requires 4D image latents or 5D latents with one frame; multi-frame and nested latents are not supported.')
            factor = parameters['upscale_factor']
            samples = comfy.utils.common_upscale(samples, round(samples.shape[-1] * factor),
                                                 round(samples.shape[-2] * factor), parameters['upscale_method'], 'disabled')
        stage_seed = (seed + (parameters['seed_offset'] if index else 0)) % (2**64)
        if index and parameters.get('second_seed', '') != '':
            stage_seed = int(parameters['second_seed'])
        advanced = parameters['two_stage']
        if advanced and not 0 <= stage['start'] < min(stage['end'], stage['steps']):
            raise ValueError(f'Stage {index + 1}: start must be below stop and total steps (including pipe settings).')
        effective_denoise = (second_stage_denoise(parameters) if index else 1.0) if advanced else denoise
        if effective_denoise <= 0:
            continue
        add_noise = stage['add_noise'] if advanced else True
        noise = comfy.sample.prepare_noise(samples, stage_seed, batch_index) if add_noise else torch.zeros_like(samples, device='cpu')
        sigmas = qwen_sigmas(parameters, samples, stage['steps'], effective_denoise) if parameters['qwen_schedule'] else None
        if parameters['detail_daemon']:
            base = comfy.samplers.KSampler(model, steps=stage['steps'], device=model.load_device,
                                           sampler=stage['sampler_name'], scheduler=stage['scheduler'],
                                           denoise=effective_denoise, model_options=model.model_options)
            schedule = (sigmas if sigmas is not None else base.sigmas).clone()
            if advanced:
                if stage['end'] < len(schedule) - 1:
                    schedule = schedule[:stage['end'] + 1].clone()
                    if not stage['leftover']:
                        schedule[-1] = 0
                schedule = schedule[stage['start']:]
            wrapped = wrap_detail(comfy.samplers.sampler_object(stage['sampler_name']), parameters)
            samples = comfy.sample.sample_custom(model, noise, stage['cfg'], wrapped, schedule,
                                                 positive, negative, samples, noise_mask=noise_mask,
                                                 callback=callback, disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED,
                                                 seed=stage_seed)
            continue
        samples = comfy.sample.sample(
            model, noise, stage['steps'], stage['cfg'], stage['sampler_name'], stage['scheduler'],
            positive, negative, samples,
            denoise=effective_denoise, disable_noise=not add_noise,
            start_step=stage['start'] if advanced else None,
            last_step=stage['end'] if advanced else None,
            force_full_denoise=not stage['leftover'] if advanced else False,
            noise_mask=noise_mask, sigmas=sigmas, callback=callback,
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED, seed=stage_seed,
        )
    return samples


def validate_model_pair(first, second):
    formats = [getattr(getattr(model, 'model', None), 'latent_format', None) for model in (first, second)]
    if any(fmt is None for fmt in formats):
        raise ValueError('Both sampling models must provide a ComfyUI latent format.')
    a, b = formats
    if type(a) is not type(b) or any(getattr(a, key, None) != getattr(b, key, None) for key in (
        'latent_channels', 'spacial_downscale_ratio', 'temporal_downscale_ratio', 'scale_factor', 'shift_factor',
    )):
        raise ValueError('Stage 2 model must use the same latent format and scaling as the Stage 1 model. Use a compatible high/low-noise pair.')
