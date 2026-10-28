# Match each decoded region to its original pixels before feathered compositing.
import torch

from .image_color_match import CPU_METHODS, match_color, sanitize


def match_detail_crop(image: torch.Tensor, reference: torch.Tensor, mask,
                      *, method: str, strength: float) -> torch.Tensor:
    if strength == 0:
        return image
    if method not in CPU_METHODS:
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

    # Pack only the region's pixels. Context (hair/background/body) must not
    # dominate its color statistics. The ordinary paste mask handles blending.
    source = sanitize(image[0, ..., :3].detach().cpu().float())[selected]
    target = sanitize(reference[0, ..., :3].detach().cpu().float())[selected]
    grayscale = bool((target.amax(-1) - target.amin(-1)).max() <= 1 / 255)
    if grayscale:
        coefficients = source.new_tensor([.2126, .7152, .0722])
        matching_source = (source * coefficients).sum(-1, keepdim=True).expand_as(source)
        target = (target * coefficients).sum(-1, keepdim=True).expand_as(target)
    else:
        matching_source = source
    corrected = match_color(matching_source[None, None], target[None, None], method, 1.)[0, 0]
    if grayscale:
        # Numerical color-space transforms must not introduce a tint into B&W.
        corrected = corrected.mean(-1, keepdim=True).expand_as(corrected)
    result = image.clone()
    rgb = result[0, ..., :3]
    rgb[selected.to(image.device)] = torch.lerp(source, corrected, strength).to(device=image.device, dtype=image.dtype)
    return result
