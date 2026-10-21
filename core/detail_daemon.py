# Adapted from Jonseed/ComfyUI-Detail-Daemon (MIT), revision
# 39206d10849584e0b6ded943faca4dcd8747beb7. Copyright (c) 2024 Jonseed.
# ComfyUI sampler and interpolation contributions: blepping.
# Original schedule concept: https://github.com/muerrilla/sd-webui-detail-daemon
# License: ../licenses/detail-daemon-MIT.txt
# Only the schedule and sampler wrapper are integrated; no node or plotting code.
from functools import partial

import numpy as np
import torch


def make_detail_daemon_schedule(
    steps,
    start,
    end,
    bias,
    amount,
    exponent,
    start_offset,
    end_offset,
    fade,
    smooth,
):
    start = min(start, end)
    mid = start + bias * (end - start)
    multipliers = np.zeros(steps)

    start_idx, mid_idx, end_idx = [
        round(x * (steps - 1)) for x in [start, mid, end]
    ]

    start_values = np.linspace(0, 1, mid_idx - start_idx + 1)
    if smooth:
        start_values = 0.5 * (1 - np.cos(start_values * np.pi))
    start_values = start_values**exponent
    if start_values.any():
        start_values *= amount - start_offset
        start_values += start_offset

    end_values = np.linspace(1, 0, end_idx - mid_idx + 1)
    if smooth:
        end_values = 0.5 * (1 - np.cos(end_values * np.pi))
    end_values = end_values**exponent
    if end_values.any():
        end_values *= amount - end_offset
        end_values += end_offset

    multipliers[start_idx : mid_idx + 1] = start_values
    multipliers[mid_idx : end_idx + 1] = end_values
    multipliers[:start_idx] = start_offset
    multipliers[end_idx + 1 :] = end_offset
    multipliers *= 1 - fade

    return multipliers


def get_dd_schedule(
    sigma: float,
    sigmas: torch.Tensor,
    dd_schedule: torch.Tensor,
) -> float:
    sched_len = len(dd_schedule)
    if (
        sched_len < 2
        or len(sigmas) < 2
        or sigma <= 0
        or not (sigmas[-1] <= sigma <= sigmas[0])
    ):
        return 0.0
    # First, we find the index of the closest sigma in the list to what the model was
    # called with.
    deltas = (sigmas[:-1] - sigma).abs()
    idx = int(deltas.argmin())
    if (
        (idx == 0 and sigma >= sigmas[0])
        or (idx == sched_len - 1 and sigma <= sigmas[-2])
        or deltas[idx] == 0
    ):
        # Either exact match or closest to head/tail of the DD schedule so we
        # can't interpolate to another schedule item.
        return dd_schedule[idx].item()
    # If we're here, that means the sigma is in between two sigmas in the
    # list.
    idxlow, idxhigh = (idx, idx - 1) if sigma > sigmas[idx] else (idx + 1, idx)
    # We find the low/high neighbor sigmas - our sigma is somewhere between them.
    nlow, nhigh = sigmas[idxlow], sigmas[idxhigh]
    if nhigh - nlow == 0:
        # Shouldn't be possible, but just in case... Avoid divide by zero.
        return dd_schedule[idxlow].item()
    # Ratio of how close we are to the high neighbor.
    ratio = ((sigma - nlow) / (nhigh - nlow)).clamp(0, 1)
    # Mix the DD schedule high/low items according to the ratio.
    return torch.lerp(dd_schedule[idxlow], dd_schedule[idxhigh], ratio).item()


def detail_daemon_sampler(
    model: object,
    x: torch.Tensor,
    sigmas: torch.Tensor,
    *,
    dds_wrapped_sampler: object,
    dds_make_schedule: callable,
    dds_cfg_scale_override: float,
    **kwargs: dict,
) -> torch.Tensor:
    if dds_cfg_scale_override > 0:
        cfg_scale = dds_cfg_scale_override
    else:
        maybe_cfg_scale = getattr(getattr(model, "inner_model", None), "cfg", None)
        cfg_scale = (
            float(maybe_cfg_scale) if isinstance(maybe_cfg_scale, (int, float)) else 1.0
        )
    dd_schedule = torch.tensor(
        dds_make_schedule(len(sigmas) - 1),
        dtype=torch.float32,
        device="cpu",
    )
    sigmas_cpu = sigmas.detach().clone().cpu()
    sigma_max, sigma_min = float(sigmas_cpu[0]), float(sigmas_cpu[-1]) + 1e-05

    def model_wrapper(x: torch.Tensor, sigma: torch.Tensor, **extra_args: dict):
        sigma_float = float(sigma.max().detach().cpu())
        if not (sigma_min <= sigma_float <= sigma_max):
            return model(x, sigma, **extra_args)
        dd_adjustment = get_dd_schedule(sigma_float, sigmas_cpu, dd_schedule) * 0.1
        adjusted_sigma = sigma * max(1e-06, 1.0 - dd_adjustment * cfg_scale)
        return model(x, adjusted_sigma, **extra_args)

    for k in (
        "inner_model",
        "sigmas",
    ):
        if hasattr(model, k):
            setattr(model_wrapper, k, getattr(model, k))
    return dds_wrapped_sampler.sampler_function(
        model_wrapper,
        x,
        sigmas,
        **{**kwargs, **dds_wrapped_sampler.extra_options},
    )


def wrap_detail(sampler, parameters):
    # Use ComfyUI's native sampler container; no custom-node registration lookup.
    from comfy.samplers import KSAMPLER

    p = parameters
    schedule = partial(make_detail_daemon_schedule, start=p['detail_start'], end=p['detail_end'],
                       bias=p['detail_bias'], amount=p['detail_amount'], exponent=p['detail_exponent'],
                       start_offset=p['detail_start_offset'], end_offset=p['detail_end_offset'],
                       fade=p['detail_fade'], smooth=p['detail_smooth'])
    return KSAMPLER(detail_daemon_sampler, extra_options={
        'dds_wrapped_sampler': sampler, 'dds_make_schedule': schedule,
        'dds_cfg_scale_override': p['detail_cfg_scale_override'],
    }, inpaint_options=dict(sampler.inpaint_options))
