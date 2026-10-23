# Shared overlap transitions for batches and streamed still-image timelines.
import math

import torch
import torch.nn.functional as F

from .image_effects import EFFECT_TOOLTIPS, TRANSITION_EFFECTS, transition_effect
from .logger import log

BLEND_MODES = (
    "linear_blend", "ease_in_out", "filmic_crossfade", "perceptual_crossfade",
    "average", "dissolve", "pyramid_blend", "clock_wipe", "clock_wipe_ccw",
    "wipe_left", "wipe_right", "wipe_top", "wipe_bottom", "morph", *TRANSITION_EFFECTS,
)
MORPH_TOOLTIP = (
    "Morph: warp both images using bidirectional optical flow, then blend them. "
    "CPU motion estimation uses OpenCV already included with Eclipse; no model download. "
    "Best with similar framing and poses; unrelated images can stretch or ghost. "
    "Slower than a crossfade. The timeline reuses motion for the entire transition."
)
BLEND_TOOLTIPS = {**EFFECT_TOOLTIPS, "morph": MORPH_TOOLTIP}
BLEND_TOOLTIP = " ".join(EFFECT_TOOLTIPS.values()) + " " + MORPH_TOOLTIP


def validate_blend(mode, duration, *, inherit=False):
    choices = ("cut", *BLEND_MODES, *(("inherit",) if inherit else ()))
    if not isinstance(mode, str) or mode not in choices:
        raise ValueError("Select a supported blend mode.")
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 <= duration <= 60:
        raise ValueError("Blend duration must be between 0 and 60 seconds.")


def resolve_blend_mode(mode):
    if mode == "perceptual_crossfade":
        try:
            import kornia  # noqa: F401 - optional runtime availability
        except ImportError:
            log.warning("ImageBlend", "kornia is required for perceptual_crossfade; using linear_blend.")
            return "linear_blend"
    return mode


def pyramid_blend(src, dst, alpha, levels=4):
    # Blend Laplacian bands with the overlap node's per-frame alpha.
    levels = min(levels, int(math.log2(min(src.shape[1:3]))) + 1)

    def laplacian(value):
        gauss = [value.float().permute(0, 3, 1, 2)]
        for _ in range(levels - 1):
            gauss.append(F.avg_pool2d(gauss[-1], 2, 2))
        return [gauss[i] - F.interpolate(gauss[i + 1], size=gauss[i].shape[2:], mode="bilinear", align_corners=False)
                for i in range(levels - 1)] + [gauss[-1]]

    bands = [(1 - alpha) * a + alpha * b for a, b in zip(laplacian(src), laplacian(dst), strict=True)]
    result = bands[-1]
    for band in reversed(bands[:-1]):
        result = F.interpolate(result, size=band.shape[2:], mode="bilinear", align_corners=False) + band
    return result.permute(0, 2, 3, 1).to(src.dtype)


def prepare_blend(src, dst, mode, *, generator=None):
    # A still-image transition reuses the same flow at every progress value.
    if mode == "morph":
        from .image_morph import MorphPair
        if src.ndim != 4 or dst.ndim != 4 or src.shape[0] != 1 or dst.shape[0] != 1:
            raise ValueError("Prepare one image pair for a timeline morph.")
        pair = MorphPair(src[0], dst[0])
        return lambda alpha: pair.frame(alpha.item()).unsqueeze(0)
    return lambda alpha: blend_frames(src, dst, alpha, mode, generator=generator)


def blend_frames(src, dst, alpha, mode, *, generator=None):
    # BHWC tensors and [B,1,1,1] alpha; a caller can stream one frame at a time.
    if mode in TRANSITION_EFFECTS:
        if src.ndim != 4 or src.shape != dst.shape or src.shape[-1] not in (1, 3, 4) or not len(src):
            raise ValueError("Transition effects expect equally sized nonempty image batches.")
        progress = alpha.detach().cpu().reshape(-1).tolist()
        if len(progress) == 1:
            progress *= len(src)
        if len(progress) != len(src):
            raise ValueError("Supply one transition progress value per image pair.")
        result = []
        for first, second, value in zip(src, dst, progress, strict=True):
            if value <= 0 or value >= 1:
                result.append(first if value <= 0 else second)
            else:
                pixels = transition_effect(first.detach().float().cpu().numpy(), second.detach().float().cpu().numpy(), value, mode)
                result.append(torch.from_numpy(pixels).to(device=src.device, dtype=src.dtype))
        return torch.stack(result)
    if mode == "morph":
        from .image_morph import MorphPair
        if src.ndim != 4 or src.shape != dst.shape or not len(src):
            raise ValueError("Morph expects equally sized nonempty image batches.")
        progress = alpha.detach().cpu().reshape(-1).tolist()
        if len(progress) not in (1, len(src)):
            raise ValueError("Supply one morph progress value per image pair.")
        if len(progress) == 1:
            progress *= len(src)
        # Overlap batches have distinct pairs: estimate each independently and
        # release its motion fields before processing the next one.
        return torch.stack([MorphPair(first, second).frame(value) for first, second, value in zip(src, dst, progress, strict=True)])
    if mode == "linear_blend":
        return (1 - alpha) * src + alpha * dst
    if mode == "ease_in_out":
        eased = 3 * alpha * alpha - 2 * alpha * alpha * alpha
        return (1 - eased) * src + eased * dst
    if mode == "filmic_crossfade":
        return ((1 - alpha) * src.clamp(min=0).pow(2.2) + alpha * dst.clamp(min=0).pow(2.2)).clamp(min=0).pow(1 / 2.2)
    if mode == "perceptual_crossfade":
        import kornia
        first, second = kornia.color.rgb_to_lab(src.movedim(-1, 1)), kornia.color.rgb_to_lab(dst.movedim(-1, 1))
        return kornia.color.lab_to_rgb((1 - alpha) * first + alpha * second).movedim(1, -1)
    if mode == "average":
        return .5 * src + .5 * dst
    if mode == "pyramid_blend":
        return pyramid_blend(src, dst, alpha)
    count, height, width, _ = src.shape
    if mode == "dissolve":
        mask = torch.rand(count, height, width, 1, device=src.device, dtype=src.dtype, generator=generator) < alpha
    elif mode in ("clock_wipe", "clock_wipe_ccw"):
        y, x = torch.meshgrid(torch.arange(height, device=src.device, dtype=torch.float32),
                              torch.arange(width, device=src.device, dtype=torch.float32), indexing="ij")
        angle = (torch.atan2(x - (width - 1) / 2, (height - 1) / 2 - y) + 2 * math.pi) % (2 * math.pi)
        if mode == "clock_wipe_ccw":
            angle = (2 * math.pi - angle) % (2 * math.pi)
        mask = angle[None, ..., None] < alpha.float() * (2 * math.pi)
    elif mode in ("wipe_left", "wipe_right", "wipe_top", "wipe_bottom"):
        horizontal = mode in ("wipe_left", "wipe_right")
        size = width if horizontal else height
        coords = torch.arange(size, device=src.device, dtype=torch.float32) / size
        if mode in ("wipe_right", "wipe_bottom"):
            coords = 1 - coords
        mask = coords.view(1, 1, width, 1) < alpha.float() if horizontal else coords.view(1, height, 1, 1) < alpha.float()
    else:
        raise ValueError(f"Unsupported blend mode: {mode}")
    return torch.where(mask, dst, src)
