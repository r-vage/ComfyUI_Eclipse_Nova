# Optional advanced-sampler controls and execution adapters.
import math

import torch


def extra_fields():
    fields = {}

    def add(key, label, default, tooltip, **limits):
        fields[key] = {"label": label, "default": default, "tooltip": tooltip, "optional": True, **limits}

    add('qwen_schedule', 'Qwen schedule', False, 'Generate Qwen Image 2.1 sigmas for each stage using its steps and actual latent resolution. Replaces the scheduler dropdown. Requires a 64-channel image latent.')
    add('dit_guidance', 'DiT skip guidance', False, 'Patch a cloned model to skip selected DiT blocks in the unconditional pass. Usually has no effect at CFG 1. Applies to both stages; the input model remains unchanged.')
    add('detail_daemon', 'Detail Daemon', False, 'Apply the built-in Detail Daemon wrapper to each stage sampler. Adjusts noise levels seen by the model while retaining the sampler schedule. No additional custom node is required.')
    add('qwen_dynamic', 'Dynamic shifting', True, 'Calculate shift from latent image tokens. Disable to use Fixed shift.')
    add('qwen_shift_type', 'Shift transform', 'exponential', 'Exponential is the Qwen Image 2.1 default. Linear uses the interpolated shift directly.', options=['exponential', 'linear'])
    for key, label, value, low, high, tip in [
        ('base_tokens', 'Base image tokens', 256, 1, 4194304, 'Lower token-count anchor. One token corresponds to a 16×16 pixel region.'),
        ('max_tokens', 'Max image tokens', 8192, 2, 4194304, 'Upper token-count anchor. Must exceed Base image tokens. Larger images extrapolate beyond this anchor.'),
        ('base_shift', 'Base shift', 0.5, 0, 100, 'Shift at the base token count; interpolated toward Max shift for larger images.'),
        ('max_shift', 'Max shift', 0.9, 0, 100, 'Shift at the max token count. With exponential shifting this is the exponent, not a direct multiplier.'),
        ('terminal', 'Terminal sigma', 0.02, 0, 0.999, 'Last positive noise level before the final zero. 0 disables stretching. Type precise values such as 0.02 directly.'),
        ('shift', 'Fixed shift', 1.0, 0.1, 100, 'Multiplicative shift used only when Dynamic shifting is disabled.'),
    ]:
        add('qwen_' + key, label, value, tip, min=low, max=high, step=1 if isinstance(value, int) else 0.01, integer=isinstance(value, int))
    for key, label, value in [('double_layers', 'Double-stream layers', ''), ('single_layers', 'Single-stream layers', '22')]:
        add('dit_' + key, label, value, 'Zero-based DiT block indices separated by commas, e.g. 7, 8, 9. Empty skips no blocks in this stream. Indices depend on the model architecture.', text=True)
    for key, label, value in [('start', 'Start fraction', 0.0), ('end', 'End fraction', 0.5)]:
        add('dit_' + key, label, value, 'Fraction of the full model noise trajectory (0–1), not the selected stage step range. Start must be below End.', min=0, max=1, step=0.1)
    for key, label, value, low, high, tip in [
        ('amount', 'Detail amount', 0.15, -5, 5, 'Positive values enhance detail; negative values soften it. Strong values can introduce artifacts. Type precise values such as 0.15 directly.'),
        ('start', 'Start fraction', 0.1, 0, 1, 'Begin the detail effect at this fraction of each stage’s executed sampling schedule.'),
        ('end', 'End fraction', 0.8, 0, 1, 'End the detail effect at this fraction of each stage’s executed schedule. Must exceed Start.'),
        ('bias', 'Peak position', 0.5, 0, 1, 'Position of the peak between Start and End. 0.5 places it halfway through the active interval.'),
        ('exponent', 'Curve exponent', 1.0, 0, 10, 'Shapes the detail curve. 1 keeps its base shape; larger values concentrate the effect around the peak.'),
        ('start_offset', 'Start offset', 0.0, -1, 1, 'Detail amount before Start and at the beginning of the active interval.'),
        ('end_offset', 'End offset', 0.0, -1, 1, 'Detail amount at End and afterward.'),
        ('fade', 'Fade', 0.0, 0, 1, 'Scale the entire effect down: 0 keeps full strength; 1 fades it completely to zero.'),
        ('cfg_scale_override', 'CFG scale override', 0.0, 0, 100, '0 lets Detail Daemon use the stage CFG. A positive value changes only detail-effect scaling, not the sampler CFG.'),
    ]:
        add('detail_' + key, label, value, tip, min=low, max=high, step=0.01)
    add('detail_smooth', 'Smooth curve', True, 'Use smooth transitions for the detail curve rather than linear ramps.')
    return fields


def qwen_sigmas(p, samples, steps, denoise):
    if samples.ndim not in (4, 5) or samples.shape[1] != 64 or (samples.ndim == 5 and samples.shape[2] != 1):
        raise ValueError('Qwen schedule requires a 64-channel image latent (one frame).')
    if denoise <= 0:
        return torch.empty(0, dtype=torch.float32)
    tokens = samples.shape[-2] * samples.shape[-1]
    shift = p['qwen_shift']
    if p['qwen_dynamic']:
        mu = p['qwen_base_shift'] + (p['qwen_max_shift'] - p['qwen_base_shift']) * (
            (tokens - p['qwen_base_tokens']) / (p['qwen_max_tokens'] - p['qwen_base_tokens']))
        if p['qwen_shift_type'] == 'exponential':
            if mu > 700:
                raise ValueError('Qwen shift is too large for this resolution.')
            shift = math.exp(mu)
        else:
            shift = mu
    if not math.isfinite(shift) or shift <= 0:
        raise ValueError('Qwen shift must be finite and positive at the current resolution.')
    total = steps / denoise
    if not math.isfinite(total):
        raise ValueError('Denoise is too small for the Qwen schedule.')
    sigma = torch.arange(steps, 0, -1, dtype=torch.float64) / int(total)
    sigma = shift * sigma / (1 + (shift - 1) * sigma)
    if p['qwen_terminal'] > 0 and int(total) > 1:
        gap = 1 - sigma[-1]
        if gap <= 0:
            raise ValueError('Qwen shift is too large for terminal stretching.')
        sigma = 1 - (1 - sigma) * (1 - p['qwen_terminal']) / gap
    sigma = torch.cat((sigma, sigma.new_zeros(1))).float()
    if not torch.isfinite(sigma).all() or (sigma[:-1] <= sigma[1:]).any():
        raise ValueError('Qwen settings must produce a finite descending schedule.')
    return sigma


def prepare_extras(p, model):
    if p['dit_guidance']:
        from comfy_extras.nodes_slg import SkipLayerGuidanceDiTSimple
        model = SkipLayerGuidanceDiTSimple.execute(
            model, p['dit_start'], p['dit_end'], p['dit_double_layers'], p['dit_single_layers']).result[0]
    return model
