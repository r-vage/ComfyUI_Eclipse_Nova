# Bound live-preview work independently from full-resolution sampling and decoding.
import math
from itertools import pairwise

import latent_preview
import torch
from PIL import Image

from .logger import log


def preview_resolution():
    return max(64, min(512, int(getattr(latent_preview, 'MAX_PREVIEW_RESOLUTION', 512))))


def preview_latent(model, x0, previewer, *, detail_scale=1):
    if x0.is_nested:
        x0 = x0.tensors[0] if hasattr(x0, 'tensors') else x0.unbind()[0]
    if x0.ndim not in (4, 5):
        return x0
    # ComfyUI's built-in previewers display only the first image/frame.
    preview = x0[:1] if x0.ndim == 4 else x0[:1, :, :1]
    latent_format = getattr(getattr(model, 'model', None), 'latent_format', None)
    downscale = getattr(latent_format, 'spacial_downscale_ratio', 8)
    if isinstance(previewer, latent_preview.Latent2RGBPreviewer):
        # RGB projection displays latent pixels directly; a VAE's compression
        # ratio would unnecessarily shrink them again (e.g. 128 px to 32 px).
        downscale = 1
        if getattr(previewer, 'latent_rgb_factors_reshape', None) is not None:
            # Packed formats such as Flux2 unpack channels into spatial pixels.
            downscale = max(1, math.sqrt(preview.shape[1] / previewer.latent_rgb_factors.shape[1]))
    if not isinstance(downscale, (int, float)) or not math.isfinite(downscale) or downscale <= 0:
        downscale = 8
    display_limit = preview_resolution() * (detail_scale if preview.ndim == 4 else 1)
    latent_limit = max(1, int(display_limit / downscale))
    height, width = preview.shape[-2:]
    if max(height, width) <= latent_limit:
        return preview
    scale = latent_limit / max(height, width)
    size = (max(1, round(height * scale)), max(1, round(width * scale)))
    frame = preview if preview.ndim == 4 else preview[:, :, 0]
    resized = torch.nn.functional.interpolate(frame, size=size, mode='bilinear', align_corners=False)
    return resized if preview.ndim == 4 else resized.unsqueeze(2)


def _tile_spans(length, tile_size):
    # The standard 8x TAESD decoder needs 20 latent pixels of context. Each
    # decode stays within 64x64 latents (512x512 pixels), including that context.
    starts = list(range(0, max(1, length - tile_size), tile_size - 40))
    if length > tile_size:
        starts.append(length - tile_size)
    bounds = [0] + [(b + min(a + tile_size, length)) // 2 for a, b in pairwise(starts)] + [length]
    return [(start, min(start + tile_size, length), bounds[i], bounds[i + 1]) for i, start in enumerate(starts)]


def _can_tile(previewer):
    # Video, packed Flux2/GroupNorm and 16x decoders retain the reduced-latent
    # path. They cannot safely use this convolution-only decoder's halo.
    if type(previewer) is not getattr(latent_preview, 'TAESDPreviewerImpl', None) or preview_resolution() < 512:
        return False
    from comfy.taesd.taesd import Decoder

    decoder = previewer.taesd.taesd_decoder
    return type(decoder) is Decoder and not any(isinstance(layer, torch.nn.GroupNorm) for layer in decoder.modules())


def decode_preview(model, x0, previewer):
    preview = preview_latent(model, x0, previewer)
    if not _can_tile(previewer) or preview.ndim != 4:
        return previewer.decode_latent_to_preview_image('JPEG', preview)
    # Keep each tile's pixel area within the previous reduced preview's budget,
    # including portrait/landscape frames. Very narrow frames keep that path.
    tile_size = min(64, math.isqrt(preview.shape[-2] * preview.shape[-1]))
    if tile_size < 48:
        return previewer.decode_latent_to_preview_image('JPEG', preview)
    preview = preview_latent(model, x0, previewer, detail_scale=2)
    if max(preview.shape[-2:]) <= tile_size:
        return previewer.decode_latent_to_preview_image('JPEG', preview)

    # Assemble at most 1024x1024 RGB pixels on the CPU, then resize the image,
    # rather than losing the latent's detail before the neural decoder sees it.
    height, width = preview.shape[-2:]
    result = Image.new('RGB', (width * 8, height * 8))
    for sy, ey, y0, y1 in _tile_spans(height, tile_size):
        for sx, ex, left, right in _tile_spans(width, tile_size):
            tile = previewer.decode_latent_to_preview(preview[..., sy:ey, sx:ex])
            crop = ((left - sx) * 8, (y0 - sy) * 8, (right - sx) * 8, (y1 - sy) * 8)
            result.paste(tile.crop(crop), (left * 8, y0 * 8))
    result.thumbnail((preview_resolution(), preview_resolution()), Image.Resampling.BILINEAR)
    return ('JPEG', result, preview_resolution())


class PreviewCallback:
    def __init__(self, model, steps):
        from comfy.utils import ProgressBar

        self.model = model
        self.progress = ProgressBar(steps)
        self.previewer = None
        self.initialized = False
        self.disabled = False

    def release(self):
        previewer, self.previewer = self.previewer, None
        self.initialized = False
        if previewer is None:
            return
        neural = isinstance(previewer, getattr(latent_preview, 'TAESDPreviewerImpl', ()))
        if isinstance(previewer, getattr(latent_preview, 'TAEHVPreviewerImpl', ())):
            # Video tiny VAEs register with ComfyUI's model manager. Unload only
            # this preview VAE; never evict the diffusion or final-decode model.
            from comfy.model_management import unload_model_and_clones

            unload_model_and_clones(previewer.taesd.patcher, unload_additional_models=False)
        del previewer
        if neural:
            from comfy.model_management import soft_empty_cache

            soft_empty_cache()

    def start_stage(self, model, steps):
        from comfy.utils import ProgressBar

        self.release()
        self.model = model
        # Native progress throttling needs a fresh counter when step numbers
        # restart, especially when an earlier preview OOM has disabled frames.
        self.progress = ProgressBar(steps)

    @torch.no_grad()
    def __call__(self, step, x0, x, total_steps):
        preview_bytes = None
        failed = False
        try:
            if not self.initialized and not self.disabled:
                # Allocate only once sampling has begun, after ComfyUI prepares
                # the diffusion model. No preview weights span the upscale.
                self.initialized = True
                self.previewer = latent_preview.get_previewer(self.model.load_device, self.model.model.latent_format)
            if self.previewer is not None:
                preview_bytes = decode_preview(self.model, x0, self.previewer)
        except torch.OutOfMemoryError:
            self.disabled = True
            failed = True
        if failed:
            # Release after leaving the exception scope, whose traceback can
            # otherwise keep failed decoder activations alive during cleanup.
            self.release()
            from comfy.model_management import soft_empty_cache

            soft_empty_cache()
            log.warning('Sampler Preview', 'Live preview ran out of memory and is disabled for this sampling run. '
                        'Sampling and final decoding continue.')
        self.progress.update_absolute(step + 1, total_steps, preview_bytes)


def prepare_callback(model, steps):
    return PreviewCallback(model, steps)
