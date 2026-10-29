# Reference color transfer; CPU algorithms derive from KJNodes ColorMatch.
import numpy as np
import torch
from comfy import model_management

from .image_soften import _haar_decompose, _haar_reconstruct, _pad
from .logger import log

_LOG_PREFIX = "ImageColorMatch"
CPU_METHODS = ("mkl", "hm", "reinhard", "mvgd", "hm-mvgd-hm", "hm-mkl-hm")
COLOR_MATCH_METHODS = (*CPU_METHODS, "reinhard_lab_gpu", "wavelet", "scattersort")


def _wavelet_statistics(channel, weights):
    if weights is None:
        return channel.mean(), channel.std(unbiased=False)
    count = weights.sum().clamp_min(1e-6)
    mean = (channel * weights).sum() / count
    variance = ((channel - mean).square() * weights).sum() / count
    return mean, variance.sqrt()


def _wavelet_color_transfer(src_bchw, ref_bchw, strength, mask=None):
    # Transfer color via Haar wavelets: match LL band statistics, keep detail bands.
    # Operates in LAB space for perceptually uniform transfer.
    import kornia  # type: ignore

    src_lab = kornia.color.rgb_to_lab(src_bchw)

    # Resize ref to match src dimensions (we only need color statistics, not spatial layout)
    _, _, src_H, src_W = src_bchw.shape
    _, _, ref_H, ref_W = ref_bchw.shape
    if ref_H != src_H or ref_W != src_W:
        ref_resized = torch.nn.functional.interpolate(
            ref_bchw, size=(src_H, src_W), mode="bilinear", align_corners=False
        )
    else:
        ref_resized = ref_bchw
    ref_lab = kornia.color.rgb_to_lab(ref_resized)

    B = src_lab.shape[0]
    _, _, H, W = src_lab.shape

    # Pad to even dimensions if needed
    pad_h = H % 2
    pad_w = W % 2
    if pad_h or pad_w:
        src_lab = _pad(src_lab, (0, pad_w, 0, pad_h))
        ref_lab = _pad(ref_lab, (0, pad_w, 0, pad_h))

    block_weights = None
    if mask is not None:
        # Keep the 2-D Haar neighborhoods. Fill only unselected pixels inside
        # each block with its selected mean so outside context cannot affect
        # either the low-frequency statistics or the selected detail bands.
        mask = torch.nn.functional.pad(mask, (0, pad_w, 0, pad_h))
        block_weights = torch.nn.functional.avg_pool2d(mask, 2)

        def masked_blocks(lab):
            means = torch.nn.functional.avg_pool2d(lab * mask, 2) / block_weights.clamp_min(1e-6)
            fill = torch.nn.functional.interpolate(means, scale_factor=2, mode="nearest")
            return torch.where(mask.bool(), lab, fill)

        src_lab, ref_lab = masked_blocks(src_lab), masked_blocks(ref_lab)

    src_LL, src_LH, src_HL, src_HH = _haar_decompose(src_lab)
    ref_LL, _, _, _ = _haar_decompose(ref_lab)

    # AdaIN on LL band: normalize src LL, scale/shift by ref LL statistics
    for b in range(B):
        ref_idx = min(b, ref_LL.shape[0] - 1)
        weights = block_weights[b, 0] if block_weights is not None else None
        for c in range(3):  # L, A, B channels
            s_mean, s_std = _wavelet_statistics(src_LL[b, c], weights)
            r_mean, r_std = _wavelet_statistics(ref_LL[ref_idx, c], weights)
            src_LL[b, c] = (src_LL[b, c] - s_mean) / s_std.clamp_min(1e-6) * r_std.clamp_min(1e-6) + r_mean

    # Reconstruct with matched LL + original detail bands
    out_lab = _haar_reconstruct(src_LL, src_LH, src_HL, src_HH)

    # Remove padding
    if pad_h or pad_w:
        out_lab = out_lab[:, :, :H, :W]

    out_rgb = kornia.color.lab_to_rgb(out_lab)

    # Apply strength blending
    if strength != 1.0:
        out_rgb = (1.0 - strength) * src_bchw + strength * out_rgb

    return out_rgb.clamp_(0, 1)


def _scattersort_transfer(src_bchw, ref_bchw, strength):
    # Per-channel histogram matching via sort-scatter.
    B, C, H, W = src_bchw.shape
    src_flat = src_bchw.reshape(B, C, -1)  # [B, C, N]
    ref_flat = ref_bchw.reshape(ref_bchw.shape[0], C, -1)

    out_flat = src_flat.clone()
    for b in range(B):
        ref_idx = min(b, ref_flat.shape[0] - 1)
        for c in range(C):
            src_ch = src_flat[b, c]  # [N]
            ref_ch = ref_flat[ref_idx, c]

            # Sort reference values
            ref_sorted = ref_ch.sort()[0]

            # If different pixel counts, interpolate reference distribution
            if src_ch.numel() != ref_ch.numel():
                # Resample ref distribution to src length
                ref_sorted = torch.nn.functional.interpolate(
                    ref_sorted.unsqueeze(0).unsqueeze(0),
                    size=src_ch.numel(),
                    mode="linear",
                    align_corners=True,
                ).reshape(-1)

            # Get sort indices for src, scatter ref sorted values back
            src_idx = src_ch.argsort()
            out_flat[b, c].scatter_(0, src_idx, ref_sorted)

    if strength != 1.0:
        out_flat = (1.0 - strength) * src_flat + strength * out_flat

    return out_flat.reshape(B, C, H, W).clamp_(0, 1)


def sanitize(image):
    return torch.nan_to_num(image, nan=0, posinf=1, neginf=0).clamp(0, 1)


def match_color(image, reference, method, strength, *, wavelet_mask=None):
    if strength == 0:
        return image
    # Both inputs belong to upstream nodes; never let a matcher mutate them.
    image, reference = sanitize(image), sanitize(reference)
    if method in CPU_METHODS:
        from color_matcher import ColorMatcher

        base = image[0].cpu().float().numpy().copy()
        source, ref = base.copy(), reference[0].cpu().float().numpy().copy()
        if method == "reinhard":
            np.maximum(source, 1 / 255, out=source)
            np.maximum(ref, 1 / 255, out=ref)
        try:
            result = ColorMatcher().transfer(src=source, ref=ref, method=method)
            if result.shape != base.shape or not np.isfinite(result).all():
                raise ValueError("Matcher returned non-finite pixels or an invalid shape")
        except (ValueError, RuntimeError, ArithmeticError, np.linalg.LinAlgError) as error:
            log.warning(_LOG_PREFIX, f"{method}: {error}; keeping the target colors.")
            return image
        return sanitize(torch.from_numpy(base + strength * (result - base)).unsqueeze(0).float())
    import kornia

    device = model_management.get_torch_device()
    source, ref = [item.to(device).movedim(-1, 1).contiguous() for item in (image, reference)]
    if method == "wavelet":
        if wavelet_mask is not None:
            if tuple(wavelet_mask.shape) != tuple(image.shape[:3]) or reference.shape[:3] != image.shape[:3]:
                raise ValueError("Masked wavelet matching requires aligned images and a BHW mask.")
            wavelet_mask = wavelet_mask.to(device=device, dtype=source.dtype).unsqueeze(1)
        result = _wavelet_color_transfer(source, ref, strength, wavelet_mask)
    elif method == "scattersort":
        result = _scattersort_transfer(source, ref, strength)
    else:
        source_lab, ref_lab = [kornia.color.rgb_to_lab(item) for item in (source, ref)]
        source_std, source_mean = torch.std_mean(source_lab.flatten(2), dim=-1, keepdim=True, unbiased=False)
        ref_std, ref_mean = torch.std_mean(ref_lab.flatten(2), dim=-1, keepdim=True, unbiased=False)
        corrected = ((source_lab.flatten(2) - source_mean) * ref_std / source_std.clamp_min(1e-6) + ref_mean).reshape_as(source_lab)
        result = torch.lerp(source, kornia.color.lab_to_rgb(corrected), strength)
    return sanitize(result.movedim(1, -1).cpu().float())

