# RGB grading and finishing operations for the combined image panel.
from functools import lru_cache
from pathlib import Path

import torch


@lru_cache(maxsize=4)
def _load_lut(path, modified, size_bytes):
    del modified
    if size_bytes > 64 * 1024 * 1024:
        raise ValueError("LUT files must be at most 64 MB.")
    size, values = None, []
    low, high = [0., 0., 0.], [1., 1., 1.]
    with open(path, encoding="utf-8-sig") as handle:
        for line in handle:
            parts = line.split("#", 1)[0].split()
            if not parts or parts[0] == "TITLE":
                continue
            if parts[0] == "LUT_3D_SIZE":
                size = int(parts[1])
                if not 2 <= size <= 128:
                    raise ValueError("3D LUT size must be between 2 and 128.")
            elif parts[0] == "DOMAIN_MIN":
                low = [float(item) for item in parts[1:]]
            elif parts[0] == "DOMAIN_MAX":
                high = [float(item) for item in parts[1:]]
            elif parts[0] == "LUT_1D_SIZE":
                raise ValueError("Select a 3D .cube LUT; 1D LUTs are unsupported.")
            elif len(parts) == 3:
                if size is None or len(values) >= size ** 3:
                    raise ValueError("LUT data must follow LUT_3D_SIZE and match its size.")
                values.append([float(item) for item in parts])
            else:
                raise ValueError("Unrecognized .cube LUT row.")
    if size is None or len(values) != size ** 3 or len(low) != 3 or len(high) != 3:
        raise ValueError("Incomplete 3D .cube LUT.")
    data, low, high = torch.tensor(values), torch.tensor(low), torch.tensor(high)
    if not all(torch.isfinite(item).all() for item in (data, low, high)) or (high <= low).any():
        raise ValueError("LUT values and domain must be finite, with maximum above minimum.")
    return data.reshape(size, size, size, 3).permute(3, 0, 1, 2).unsqueeze(0), low, high


def load_lut(path):
    stat = Path(path).stat()
    return _load_lut(str(path), stat.st_mtime_ns, stat.st_size)


def apply_lut(image, lut, strength):
    data, low, high = (item.to(image) for item in lut)
    grid = ((image - low) / (high - low)).clamp(0, 1) * 2 - 1
    result = torch.nn.functional.grid_sample(data.expand(image.shape[0], -1, -1, -1, -1), grid.unsqueeze(1),
                                             mode="bilinear", padding_mode="border", align_corners=True)
    return torch.lerp(image, result.squeeze(2).permute(0, 2, 3, 1), strength).clamp(0, 1)

def rgb_to_hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    max_val, max_idx = torch.max(rgb, dim=-1)
    min_val, _ = torch.min(rgb, dim=-1)
    d = max_val - min_val

    eps = 1e-7
    d_safe = torch.where(
        d == 0.0, torch.tensor(eps, device=rgb.device, dtype=rgb.dtype), d
    )

    r_max = max_idx == 0
    g_max = max_idx == 1
    b_max = max_idx == 2

    h = torch.zeros_like(max_val)
    h[r_max] = (((g[r_max] - b[r_max]) / d_safe[r_max]) % 6) / 6.0
    h[g_max] = (((b[g_max] - r[g_max]) / d_safe[g_max]) + 2) / 6.0
    h[b_max] = (((r[b_max] - g[b_max]) / d_safe[b_max]) + 4) / 6.0

    s = torch.zeros_like(max_val)
    max_val_safe = torch.where(
        max_val == 0.0, torch.tensor(eps, device=rgb.device, dtype=rgb.dtype), max_val
    )
    s = d / max_val_safe

    v = max_val

    return torch.stack((h, s, v), dim=-1)


def hsv_to_rgb(hsv):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    c = v * s
    x = c * (1.0 - torch.abs((h * 6.0) % 2.0 - 1.0))
    m = v - c

    h_mod = (h * 6.0).to(torch.int32) % 6

    r = torch.zeros_like(h)
    g = torch.zeros_like(h)
    b = torch.zeros_like(h)

    cond = h_mod == 0
    r[cond], g[cond], b[cond] = c[cond], x[cond], 0.0

    cond = h_mod == 1
    r[cond], g[cond], b[cond] = x[cond], c[cond], 0.0

    cond = h_mod == 2
    r[cond], g[cond], b[cond] = 0.0, c[cond], x[cond]

    cond = h_mod == 3
    r[cond], g[cond], b[cond] = 0.0, x[cond], c[cond]

    cond = h_mod == 4
    r[cond], g[cond], b[cond] = x[cond], 0.0, c[cond]

    cond = h_mod == 5
    r[cond], g[cond], b[cond] = c[cond], 0.0, x[cond]

    rgb = torch.stack((r + m, g + m, b + m), dim=-1)
    return rgb


def adjust_hue(image, hue_shift):
    if hue_shift == 0.0:
        return image
    hsv = rgb_to_hsv(image)
    hsv[..., 0] = (hsv[..., 0] + (hue_shift / 360.0)) % 1.0
    return hsv_to_rgb(hsv).clamp(0.0, 1.0)


def adjust_temperature_and_tint(image, temperature, tint):
    if temperature == 0.0 and tint == 0.0:
        return image

    r = image[..., 0]
    g = image[..., 1]
    b = image[..., 2]

    if temperature != 0.0:
        if temperature > 0.0:
            r = r * (1.0 + temperature)
            g = g * (1.0 + temperature * 0.4)
        else:
            b = b * (1.0 - temperature)

    if tint != 0.0:
        if tint > 0.0:
            r = r * (1.0 + tint * 0.1)
            b = b * (1.0 + tint * 0.1)
        else:
            g = g * (1.0 - tint * 0.1)

    return torch.stack((r, g, b), dim=-1).clamp(0.0, 1.0)


def apply_vignette(image, intensity, center_x, center_y):
    if intensity <= 0.0:
        return image

    _, H, W, _ = image.shape
    device = image.device
    dtype = image.dtype

    y = torch.linspace(0, 1, H, device=device, dtype=dtype)
    x = torch.linspace(0, 1, W, device=device, dtype=dtype)
    grid_y, grid_x = torch.meshgrid(y, x, indexing="ij")

    dist = torch.sqrt((grid_x - center_x) ** 2 + (grid_y - center_y) ** 2)
    max_dist = torch.sqrt(
        torch.tensor(
            max(center_x, 1.0 - center_x) ** 2 + max(center_y, 1.0 - center_y) ** 2,
            device=device,
            dtype=dtype,
        )
    )
    dist = dist / max_dist

    mask = 1.0 - intensity * (dist**2)
    mask = torch.clamp(mask, 0.0, 1.0).view(1, H, W, 1)

    return image * mask


def apply_film_grain(image, strength, size, saturation):
    if strength <= 0.0:
        return image

    B, H, W, _ = image.shape
    device = image.device
    dtype = image.dtype

    if size > 1.0:
        noise_h = max(2, int(H / size))
        noise_w = max(2, int(W / size))
    else:
        noise_h, noise_w = H, W

    gray_noise = torch.randn(B, noise_h, noise_w, 1, device=device, dtype=dtype)

    if saturation > 0.0:
        color_noise = torch.randn(B, noise_h, noise_w, 3, device=device, dtype=dtype)
        noise = torch.lerp(gray_noise, color_noise, saturation)
    else:
        noise = gray_noise.expand(-1, -1, -1, 3)

    if size > 1.0:
        noise = noise.movedim(-1, 1)
        noise = torch.nn.functional.interpolate(
            noise, size=(H, W), mode="bilinear", align_corners=False
        )
        noise = noise.movedim(1, -1)

    lum = (image * torch.tensor([0.299, 0.587, 0.114], device=device, dtype=dtype)).sum(
        dim=-1, keepdim=True
    )
    grain_mask = 4.0 * lum * (1.0 - lum)

    grain = noise * strength * grain_mask
    return torch.clamp(image + grain, 0.0, 1.0)


def apply_solarize(image, threshold):
    if threshold <= 0.0:
        return image
    return torch.where(image < threshold, image, 1.0 - image)


def apply_chromatic_aberration(image, ca_amount):
    if ca_amount <= 0.0:
        return image

    B, H, W, _ = image.shape
    device = image.device
    dtype = image.dtype

    img_bchw = image.movedim(-1, 1)

    y = torch.linspace(-1, 1, H, device=device, dtype=dtype)
    x = torch.linspace(-1, 1, W, device=device, dtype=dtype)
    grid_y, grid_x = torch.meshgrid(y, x, indexing="ij")
    grid = torch.stack((grid_x, grid_y), dim=-1).unsqueeze(0).expand(B, -1, -1, -1)

    shift = ca_amount * 0.02
    grid_r = grid * (1.0 - shift)
    out_r = torch.nn.functional.grid_sample(
        img_bchw[:, 0:1],
        grid_r,
        mode="bilinear",
        padding_mode="border",
        align_corners=True,
    )

    out_g = img_bchw[:, 1:2]

    grid_b = grid * (1.0 + shift)
    out_b = torch.nn.functional.grid_sample(
        img_bchw[:, 2:3],
        grid_b,
        mode="bilinear",
        padding_mode="border",
        align_corners=True,
    )

    out_img = torch.cat((out_r, out_g, out_b), dim=1).movedim(1, -1)
    return out_img

