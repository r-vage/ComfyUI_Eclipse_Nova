# Configuration and display formatting for the DOM previews with optional Stop.

import json

import nodes
import torch
from torch._tensor_str import printoptions

from .image_helpers import flatten_images, flatten_masks, unwrap_value

WIDGET_TYPE = "ECLIPSE_NOVA_REVIEW_PREVIEW"
DEFAULT_CONFIGURATION = json.dumps({"version": 1, "stop": False})


def validate_configuration(raw):
    raw = unwrap_value(raw)
    if not isinstance(raw, str) or len(raw) > 1024:
        raise ValueError("Preview configuration must be a JSON string of at most 1 KB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid preview configuration JSON.") from error
    if not isinstance(config, dict) or config.keys() != {"version", "stop"}:
        raise ValueError("Invalid preview configuration fields.")
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 preview configuration.")
    if type(config["stop"]) is not bool:
        raise ValueError("Stop must be true or false.")
    return config


def format_value(value):
    # Keep the original Show Any text representation without changing the data.
    try:
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool, list, dict)):
            return str(value)
        if isinstance(value, torch.Tensor):
            with printoptions(edgeitems=6):
                return str(value)
        if isinstance(value, tuple):
            if value and isinstance(value[0], torch.Tensor):
                shapes = [list(item.shape) if isinstance(item, torch.Tensor) else type(item).__name__ for item in value]
                return f"Tuple[{len(value)} items: {shapes}]"
            return str(value)
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)
    except Exception:  # noqa: BLE001 — arbitrary input objects can raise from their string representation.
        return f"<{type(value).__name__}>"


def _preview_frames(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [frame for item in value for frame in _preview_frames(item)]
    if isinstance(value, torch.Tensor):
        # ComfyUI IMAGE is BHWC and MASK is BHW (or a single HW mask).
        # Rank, rather than width, distinguishes even masks only 3 or 4 pixels wide.
        if value.ndim in (2, 3):
            return [mask.unsqueeze(-1).expand(-1, -1, 3) for mask in flatten_masks(value)]
        if value.ndim == 4 and value.shape[-1] in (3, 4):
            return [frame[0] for frame in flatten_images(value)]
    raise ValueError("Preview expects RGB or RGBA images [batch, height, width, channels] or masks [batch, height, width] / [height, width].")


def image_preview(images, prompt=None, extra_pnginfo=None):
    frames = _preview_frames(images)
    if not frames:
        return {"images": []}
    # ComfyUI handles unique temporary PNG names and workflow metadata. Flatten
    # and convert only preview frames; original image/mask batches pass through.
    return nodes.PreviewImage().save_images(
        [frame.detach() for frame in frames], prompt=prompt, extra_pnginfo=extra_pnginfo,
    )["ui"]
