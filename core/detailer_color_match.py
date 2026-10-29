# Match each decoded region to its original pixels before feathered compositing.
import torch

from .image_color_match import COLOR_MATCH_METHODS, match_color, sanitize


def match_detail_crop(image: torch.Tensor, reference: torch.Tensor, mask,
                      *, method: str, strength: float) -> torch.Tensor:
    if strength == 0:
        return image
    if method not in COLOR_MATCH_METHODS:
        raise ValueError('Unsupported detailer color-match method.')
    if (image.ndim != 4 or reference.ndim != 4 or image.shape[0] != 1
            or image.shape[:3] != reference.shape[:3]
            or image.shape[-1] not in (3, 4) or reference.shape[-1] not in (3, 4)):
        raise ValueError('Detailer color matching requires aligned single RGB/RGBA crops.')
    weights = torch.as_tensor(mask, dtype=torch.float32, device='cpu')
    if weights.numel() != image.shape[1] * image.shape[2]:
        raise ValueError('Detailer color-match mask must match the crop size.')
    selected = torch.nan_to_num(weights.reshape(image.shape[1:3]), nan=0, posinf=0, neginf=0) > 0
    if reference.shape[-1] == 4:
        selected &= reference[0, ..., 3].detach().cpu() > 0
    if not selected.any():
        return image

    # Statistical methods can pack the region pixels; Wavelet must keep their
    # spatial layout. Both exclude context from the matching statistics.
    source_rgb = sanitize(image[0, ..., :3].detach().cpu().float())
    target_rgb = sanitize(reference[0, ..., :3].detach().cpu().float())
    source, target = source_rgb[selected], target_rgb[selected]
    grayscale = bool((target.amax(-1) - target.amin(-1)).max() <= 1 / 255)
    matching_source = source_rgb if method == 'wavelet' else source
    target = target_rgb if method == 'wavelet' else target
    if grayscale:
        coefficients = source.new_tensor([.2126, .7152, .0722])
        matching_source = (matching_source * coefficients).sum(-1, keepdim=True).expand_as(matching_source)
        target = (target * coefficients).sum(-1, keepdim=True).expand_as(target)
    if method == 'wavelet':
        # A full mask uses precisely the standalone node's edge handling.
        mask = None if selected.all() else selected[None]
        corrected = match_color(matching_source[None], target[None], method, 1., wavelet_mask=mask)[0, selected]
    else:
        corrected = match_color(matching_source[None, None], target[None, None], method, 1.)[0, 0]
    if grayscale:
        # Numerical color-space transforms must not introduce a tint into B&W.
        corrected = corrected.mean(-1, keepdim=True).expand_as(corrected)
    result = image.clone()
    rgb = result[0, ..., :3]
    rgb[selected.to(image.device)] = torch.lerp(source, corrected, strength).to(device=image.device, dtype=image.dtype)
    return result
