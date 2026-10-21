# Bound live-preview work independently from full-resolution sampling and decoding.
import math

import latent_preview
import torch

from .logger import log


def preview_latent(model, x0):
    if x0.is_nested:
        x0 = x0.tensors[0] if hasattr(x0, 'tensors') else x0.unbind()[0]
    if x0.ndim not in (4, 5):
        return x0
    # ComfyUI's built-in previewers display only the first image/frame.
    preview = x0[:1] if x0.ndim == 4 else x0[:1, :, :1]
    latent_format = getattr(getattr(model, 'model', None), 'latent_format', None)
    downscale = getattr(latent_format, 'spacial_downscale_ratio', 8)
    if not isinstance(downscale, (int, float)) or not math.isfinite(downscale) or downscale <= 0:
        downscale = 8
    display_limit = max(64, min(512, int(getattr(latent_preview, 'MAX_PREVIEW_RESOLUTION', 512))))
    latent_limit = max(1, int(display_limit / downscale))
    height, width = preview.shape[-2:]
    if max(height, width) <= latent_limit:
        return preview
    scale = latent_limit / max(height, width)
    size = (max(1, round(height * scale)), max(1, round(width * scale)))
    frame = preview if preview.ndim == 4 else preview[:, :, 0]
    resized = torch.nn.functional.interpolate(frame, size=size, mode='bilinear', align_corners=False)
    return resized if preview.ndim == 4 else resized.unsqueeze(2)


def prepare_callback(model, steps):
    # Keep native preview selection and progress events. A preview-only OOM must
    # not discard completed sampling; subsequent steps keep progress without frames.
    native = None
    progress = None

    def disable_preview():
        nonlocal native, progress
        native = None
        from comfy.utils import ProgressBar
        progress = ProgressBar(steps)
        log.warning('Sampler Preview', 'Live preview ran out of memory and is disabled for this sampling run. Sampling and final decoding continue.')

    try:
        native = latent_preview.prepare_callback(model, steps)
    except torch.OutOfMemoryError:
        disable_preview()

    @torch.no_grad()
    def callback(step, x0, x, total_steps):
        if native is not None:
            try:
                native(step, preview_latent(model, x0), x, total_steps)
                return
            except torch.OutOfMemoryError:
                disable_preview()
        progress.update_absolute(step + 1, total_steps, None)

    return callback
