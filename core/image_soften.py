# Spatial and frequency softening, including signed unsharp masking.
import torch
from comfy import model_management
from torch.nn import functional as F


def _pad(image, padding):
    # Reflection needs each pad smaller than its dimension. Replicate tiny edges.
    left, right, top, bottom = padding
    mode = "reflect" if max(left, right) < image.shape[-1] and max(top, bottom) < image.shape[-2] else "replicate"
    return F.pad(image, padding, mode=mode)


def _windows(image, radius):
    # Bound neighborhood temporaries to about 32 MB, including large radii.
    batch, channels, height, width = image.shape
    size = 2 * radius + 1
    side = max(1, int((8_000_000 / (batch * channels * size * size * 4)) ** .5))
    padded = _pad(image, (radius, radius, radius, radius))
    for y in range(0, height, side):
        for x in range(0, width, side):
            model_management.throw_exception_if_processing_interrupted()
            h, w = min(side, height - y), min(side, width - x)
            tile = padded[:, :, y:y + h + 2 * radius, x:x + w + 2 * radius]
            yield y, x, h, w, tile.unfold(2, size, 1).unfold(3, size, 1)

def _gaussian_kernel_1d(sigma, device, dtype):
    # Create a 1D Gaussian kernel with radius = ceil(2*sigma).
    radius = max(int(sigma * 2 + 0.5), 1)
    size = 2 * radius + 1
    x = torch.arange(size, device=device, dtype=dtype) - radius
    kernel = torch.exp(-0.5 * (x / max(sigma, 1e-6)) ** 2)
    kernel = kernel / kernel.sum()
    return kernel, radius


def _gaussian_blur(img_bchw, sigma):
    # Separable Gaussian blur on BCHW tensor.
    if sigma <= 0:
        return img_bchw
    kernel, radius = _gaussian_kernel_1d(sigma, img_bchw.device, img_bchw.dtype)
    C = img_bchw.shape[1]
    # Horizontal pass
    kh = kernel.view(1, 1, 1, -1).expand(C, -1, -1, -1)
    out = _pad(img_bchw, (radius, radius, 0, 0))
    out = F.conv2d(out, kh, groups=C)
    # Vertical pass
    kv = kernel.view(1, 1, -1, 1).expand(C, -1, -1, -1)
    out = _pad(out, (0, 0, radius, radius))
    out = F.conv2d(out, kv, groups=C)
    return out


def _bilateral_filter(img_bchw, sigma_spatial, sigma_color):
    # Approximated bilateral filter using spatial Gaussian + color range weighting.
    # Works per-pixel with a local window.
    kernel, radius = _gaussian_kernel_1d(sigma_spatial, img_bchw.device, img_bchw.dtype)
    spatial_w = kernel[:, None] * kernel[None, :]
    out = torch.empty_like(img_bchw)
    for y, x, h, w, patches in _windows(img_bchw, radius):
        center = img_bchw[:, :, y:y + h, x:x + w, None, None]
        color_diff = (patches - center).square().sum(dim=1, keepdim=True)
        weights = spatial_w * torch.exp(-color_diff / (2 * max(sigma_color, 1e-6) ** 2))
        weights /= weights.sum(dim=(-2, -1), keepdim=True).clamp_min(1e-8)
        out[:, :, y:y + h, x:x + w] = (patches * weights).sum(dim=(-2, -1))
    return out


def _haar_decompose(x):
    # Orthonormal Haar wavelet decomposition.
    # [B, C, H, W] → LL, LH, HL, HH each [B, C, H//2, W//2]
    x = x.float()
    x00 = x[:, :, 0::2, 0::2]
    x01 = x[:, :, 0::2, 1::2]
    x10 = x[:, :, 1::2, 0::2]
    x11 = x[:, :, 1::2, 1::2]
    norm = 0.5 / (2**0.5)
    LL = (x00 + x01 + x10 + x11) * norm
    LH = (x00 - x01 + x10 - x11) * norm
    HL = (x00 + x01 - x10 - x11) * norm
    HH = (x00 - x01 - x10 + x11) * norm
    return LL, LH, HL, HH


def _haar_reconstruct(LL, LH, HL, HH):
    # Orthonormal inverse Haar reconstruction.
    # LL, LH, HL, HH [B, C, H, W] → [B, C, H*2, W*2]
    norm = 1.0 / (2**0.5)
    B, C, H, W = LL.shape
    x00 = (LL + LH + HL + HH) * norm
    x01 = (LL - LH + HL - HH) * norm
    x10 = (LL + LH - HL - HH) * norm
    x11 = (LL - LH - HL + HH) * norm
    out = torch.zeros(B, C, H * 2, W * 2, device=LL.device, dtype=LL.dtype)
    out[:, :, 0::2, 0::2] = x00
    out[:, :, 0::2, 1::2] = x01
    out[:, :, 1::2, 0::2] = x10
    out[:, :, 1::2, 1::2] = x11
    return out


def _wavelet_soften(img_bchw, strength):
    # Attenuate high-frequency wavelet bands (LH, HL, HH) while preserving
    # the low-frequency LL band (color/structure). strength=1 removes all detail,
    # strength=0.5 halves detail intensity.
    _, _, H, W = img_bchw.shape
    pad_h = H % 2
    pad_w = W % 2
    x = img_bchw
    if pad_h or pad_w:
        x = _pad(x, (0, pad_w, 0, pad_h))

    LL, LH, HL, HH = _haar_decompose(x)

    # Attenuate detail bands — strength=1 means full removal
    attenuation = 1.0 - strength
    LH = LH * attenuation
    HL = HL * attenuation
    HH = HH * attenuation

    out = _haar_reconstruct(LL, LH, HL, HH)

    if pad_h or pad_w:
        out = out[:, :, :H, :W]
    return out


def _median_filter(img_bchw, radius):
    # Per-channel median filter using unfold.
    r = max(int(radius), 1)
    out = torch.empty_like(img_bchw)
    for y, x, h, w, patches in _windows(img_bchw, r):
        out[:, :, y:y + h, x:x + w] = patches.flatten(-2).median(dim=-1)[0]
    return out


def _anisotropic_diffusion(img_bchw, iterations, kappa, gamma=0.1):
    # Perona-Malik anisotropic diffusion — iterative edge-preserving smoothing.
    # kappa controls edge sensitivity (higher = smoother across edges).
    # gamma is the diffusion rate per step (0 < gamma <= 0.25 for stability).
    out = img_bchw.clone()
    for _ in range(iterations):
        model_management.throw_exception_if_processing_interrupted()
        # Compute gradients in 4 directions
        dn = _pad(out, (0, 0, 0, 1))[:, :, 1:, :] - out  # North
        ds = (
            _pad(out, (0, 0, 1, 0))[:, :, :-1, :] - out
        )  # South — shift down
        de = _pad(out, (0, 1, 0, 0))[:, :, :, 1:] - out  # East
        dw = _pad(out, (1, 0, 0, 0))[:, :, :, :-1] - out  # West

        # Fix: ensure all gradient tensors match spatial dimensions
        H, W = out.shape[-2:]
        dn = dn[:, :, :H, :W]
        ds = ds[:, :, :H, :W]
        de = de[:, :, :H, :W]
        dw = dw[:, :, :H, :W]

        # Perona-Malik conductance (exponential)
        cn = torch.exp(-((dn / kappa) ** 2))
        cs = torch.exp(-((ds / kappa) ** 2))
        ce = torch.exp(-((de / kappa) ** 2))
        cw = torch.exp(-((dw / kappa) ** 2))

        out = out + gamma * (cn * dn + cs * ds + ce * de + cw * dw)

    return out.clamp_(0, 1)


def _sobel_edge_mask(img_bchw, threshold, dilation):
    # Compute gradient magnitude via Sobel, normalize, threshold, and dilate.
    # Returns a soft mask [B, 1, H, W] where 1 = edge region.
    B = img_bchw.shape[0]
    # Convert to grayscale for edge detection
    gray = img_bchw.mean(dim=1, keepdim=True)  # [B, 1, H, W]

    # Sobel kernels
    sobel_x = torch.tensor(
        [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]],
        device=img_bchw.device,
        dtype=img_bchw.dtype,
    ).view(1, 1, 3, 3)
    sobel_y = torch.tensor(
        [[-1, -2, -1], [0, 0, 0], [1, 2, 1]],
        device=img_bchw.device,
        dtype=img_bchw.dtype,
    ).view(1, 1, 3, 3)

    padded = _pad(gray, (1, 1, 1, 1))
    gx = F.conv2d(padded, sobel_x)
    gy = F.conv2d(padded, sobel_y)
    magnitude = torch.sqrt(gx**2 + gy**2)

    # Normalize to [0, 1] per image
    mag_max = magnitude.flatten(1).max(dim=1)[0].view(B, 1, 1, 1).clamp(min=1e-6)
    magnitude = magnitude / mag_max

    # Threshold — create a soft mask via sigmoid around the threshold
    # steepness=20 gives a fairly sharp but smooth transition
    mask = torch.sigmoid((magnitude - threshold) * 20)

    # Dilate the mask — expand edge regions using max pooling
    if dilation > 0:
        dil_size = 2 * dilation + 1
        mask = F.max_pool2d(mask, kernel_size=dil_size, stride=1, padding=dilation)

    return mask


def _edge_blur(img_bchw, sigma, strength, radius):
    # Apply Gaussian blur only at detected hard edges.
    # radius controls edge detection sensitivity (threshold) and dilation.
    blurred = _gaussian_blur(img_bchw, sigma)

    # threshold: lower radius = more sensitive (detects more edges)
    # Map radius 0.1-10 → threshold 0.02-0.5
    threshold = 0.02 + (radius - 0.1) * (0.48 / 9.9)
    # Dilation: expand edge mask by 1-3 pixels based on sigma
    dilation = max(1, int(sigma * 0.5 + 0.5))

    mask = _sobel_edge_mask(img_bchw, threshold, dilation)
    # Apply strength to the mask
    mask = mask * abs(strength)

    # Blend: original where mask=0, blurred where mask=1
    if strength >= 0:
        out = img_bchw * (1 - mask) + blurred * mask
    else:
        # Negative strength → sharpen at edges (unsharp mask localized to edges)
        sharpened = 2.0 * img_bchw - blurred
        out = img_bchw * (1 - mask) + sharpened * mask

    return out


def soften(image, settings):
    strength, radius, method = (settings[key] for key in ("strength", "radius", "method"))
    if strength == 0:
        return image
    img = image.to(model_management.get_torch_device()).movedim(-1, 1).contiguous()
    absolute = abs(strength)
    if method == "gaussian":
        result = _gaussian_blur(img, radius * absolute * 3)
    elif method == "bilateral":
        result = _bilateral_filter(img, radius * 2, .1 + (1 - absolute) * .4)
    elif method == "wavelet":
        result = _wavelet_soften(img, strength)
    elif method == "median":
        result = _median_filter(img, max(1, int(radius * absolute * 2 + .5)))
    elif method == "anisotropic":
        result = _anisotropic_diffusion(img, int(settings["iterations"]), .02 + (1 - absolute) * .18)
    else:
        result = _edge_blur(img, radius * 2, strength, radius)
    if method not in ("wavelet", "edge_blur"):
        result = (1 - strength) * img + strength * result
    return result.movedim(1, -1).cpu().float().clamp(0, 1)

