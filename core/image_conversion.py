# Shared tensor conversions, alpha compositing and optional style filters.
import torch  # type: ignore

from .image_helpers import hex_to_rgb_float, pil2tensor, tensor2pil

# Import pilgram for style filters
try:
    import pilgram  # type: ignore
except ImportError:
    pilgram = None


def is_rgb_tensor(tensor):
    # Check if tensor is RGB (3 channels)
    return tensor.shape[-1] == 3


def is_rgba_tensor(tensor):
    # Check if tensor is RGBA (4 channels)
    return tensor.shape[-1] == 4


def is_grayscale_tensor(tensor):
    # Check if tensor is grayscale (1 channel)
    return tensor.shape[-1] == 1


def convert_to_rgb(tensor):
    # Convert tensor to RGB
    if is_rgb_tensor(tensor):
        return tensor
    elif is_rgba_tensor(tensor):
        # Remove alpha channel
        return tensor[..., :3]
    elif is_grayscale_tensor(tensor):
        # Expand grayscale to RGB by repeating the channel
        return tensor.repeat(1, 1, 1, 3)
    else:
        raise ValueError(f"Unsupported tensor shape: {tensor.shape}")


def convert_to_grayscale(tensor):
    # Convert tensor to grayscale using luminance formula.
    # Returns RGB format (3 channels) with same grayscale value in all channels
    # to maintain ComfyUI IMAGE format compatibility.
    if is_grayscale_tensor(tensor):
        # Already grayscale, convert to 3-channel format
        return tensor.repeat(1, 1, 1, 3)
    elif is_rgb_tensor(tensor) or is_rgba_tensor(tensor):
        # Use standard luminance formula: Y = 0.299R + 0.587G + 0.114B
        rgb = tensor[..., :3]  # Use only RGB channels
        weights = torch.tensor(
            [0.299, 0.587, 0.114], dtype=tensor.dtype, device=tensor.device
        )
        grayscale = torch.sum(rgb * weights, dim=-1, keepdim=True)
        # Repeat to 3 channels for ComfyUI compatibility
        return grayscale.repeat(1, 1, 1, 3)
    else:
        raise ValueError(f"Unsupported tensor shape: {tensor.shape}")


def composite_alpha_channel(
    tensor: torch.Tensor, background_color: str
) -> torch.Tensor:
    # Flatten RGBA onto a solid background while leaving other formats unchanged.
    if not is_rgba_tensor(tensor):
        return tensor

    background = torch.tensor(
        hex_to_rgb_float(background_color),
        dtype=tensor.dtype,
        device=tensor.device,
    )
    alpha = tensor[..., 3:4]
    return tensor[..., :3] * alpha + background * (1.0 - alpha)


_STYLE_OPTIONS = [
    "none",
    "1977",
    "aden",
    "brannan",
    "brooklyn",
    "clarendon",
    "earlybird",
    "gingham",
    "hudson",
    "inkwell",
    "kelvin",
    "lark",
    "lofi",
    "maven",
    "mayfair",
    "moon",
    "nashville",
    "perpetua",
    "reyes",
    "rise",
    "slumber",
    "stinson",
    "toaster",
    "valencia",
    "walden",
    "willow",
    "xpro2",
]


_STYLE_MAP = {
    "1977": pilgram._1977,
    "aden": pilgram.aden,
    "brannan": pilgram.brannan,
    "brooklyn": pilgram.brooklyn,
    "clarendon": pilgram.clarendon,
    "earlybird": pilgram.earlybird,
    "gingham": pilgram.gingham,
    "hudson": pilgram.hudson,
    "inkwell": pilgram.inkwell,
    "kelvin": pilgram.kelvin,
    "lark": pilgram.lark,
    "lofi": pilgram.lofi,
    "maven": pilgram.maven,
    "mayfair": pilgram.mayfair,
    "moon": pilgram.moon,
    "nashville": pilgram.nashville,
    "perpetua": pilgram.perpetua,
    "reyes": pilgram.reyes,
    "rise": pilgram.rise,
    "slumber": pilgram.slumber,
    "stinson": pilgram.stinson,
    "toaster": pilgram.toaster,
    "valencia": pilgram.valencia,
    "walden": pilgram.walden,
    "willow": pilgram.willow,
    "xpro2": pilgram.xpro2,
} if pilgram is not None else {}


def _apply_style(images, style):
    # Apply Instagram-like style filter to images
    if pilgram is None:
        raise ImportError(
            "The pilgram dependency is required for Image Convert style filters. "
            "Install the Eclipse requirements and restart ComfyUI."
        )
    if style not in _STYLE_MAP:
        return images

    filter_func = _STYLE_MAP[style]
    tensors = []

    for img in images:
        styled_img = pil2tensor(filter_func(tensor2pil(img)))
        tensors.append(styled_img)

    return torch.cat(tensors, dim=0)


def convert_images(images, to_rgb=False, to_grayscale=False, composite_alpha=False,
                   background_color="#000000", style="none"):
    result = images
    if composite_alpha:
        result = composite_alpha_channel(result, background_color)
    if to_rgb:
        result = convert_to_rgb(result)
    if to_grayscale:
        result = convert_to_grayscale(result)
    if style != "none":
        result = _apply_style(result, style)
    return result
