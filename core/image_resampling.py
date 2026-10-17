# Interruptible image resizing with on-demand supersampling regions.
import math

import torch
from comfy import model_management
from PIL import Image
from torch.nn import functional

from .image_helpers import pil2tensor, tensor2pil


def check_resize_memory(width, height, channels=3, batch=1, workspace=128 * 1024 ** 2):
    model_management.throw_exception_if_processing_interrupted()
    # Allow for the result, subsequent image effects, and bounded filter work.
    required = width * height * channels * batch * 4 * 3 + workspace
    available = model_management.get_free_memory(torch.device("cpu"))
    if required > available * .75:
        raise ValueError(
            f"Image resize to {width}×{height} needs about {required / 1024 ** 3:.2f} GiB "
            f"of working RAM; only {available / 1024 ** 3:.2f} GiB is available. "
            "Reduce the image or target size, or process fewer images."
        )


def _positions(start, end, scale):
    # Match the float32 pixel-center arithmetic of ComfyUI's Torch resize.
    return (torch.arange(start, end, dtype=torch.float32) + .5) * scale - .5


def _interpolate_axis(source, positions, origin, axis, cubic):
    base = positions.floor().long()
    fraction = positions - base
    if cubic:
        # Keys' cubic kernel with a=-0.75, as used by Torch bicubic resize.
        def inner(value):
            return ((1.25 * value - 2.25) * value) * value + 1

        def outer(value):
            return ((-.75 * value + 3.75) * value - 6) * value + 3

        weights = (outer(fraction + 1), inner(fraction), inner(1 - fraction), outer(2 - fraction))
        offsets = (-1, 0, 1, 2)
    else:
        weights, offsets = (1 - fraction, fraction), (0, 1)
    shape = [1] * source.ndim
    shape[axis] = len(positions)
    result = None
    for offset, weight in zip(offsets, weights):
        model_management.throw_exception_if_processing_interrupted()
        indices = (base + offset - origin).clamp(0, source.shape[axis] - 1)
        values = source.index_select(axis, indices) * weight.reshape(shape)
        result = values if result is None else result.add_(values)
    return result


def _region(read, source_size, target_size, box, method):
    model_management.throw_exception_if_processing_interrupted()
    sw, sh = source_size
    tw, th = target_size
    x0, y0, x1, y1 = box
    sx, sy = sw / tw, sh / th
    if source_size == target_size:
        return read(box)

    if method == "nearest-exact":
        xs = torch.floor(_positions(x0, x1, sx) + .5).long().clamp(0, sw - 1)
        ys = torch.floor(_positions(y0, y1, sy) + .5).long().clamp(0, sh - 1)
        left, top, right, bottom = int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1
    elif method == "area":
        left, top = math.floor(x0 * sx), math.floor(y0 * sy)
        right, bottom = math.ceil(x1 * sx), math.ceil(y1 * sy)
    elif method == "lanczos":
        # Include the whole filter support, not just the nominal output crop.
        left, top = max(0, math.floor(x0 * sx - 3 * max(1, sx)) - 2), max(0, math.floor(y0 * sy - 3 * max(1, sy)) - 2)
        right, bottom = min(sw, math.ceil(x1 * sx + 3 * max(1, sx)) + 2), min(sh, math.ceil(y1 * sy + 3 * max(1, sy)) + 2)
    else:
        xs, ys = _positions(x0, x1, sx), _positions(y0, y1, sy)
        support = 2 if method == "bicubic" else 1
        left, top = max(0, math.floor(xs[0]) - support + 1), max(0, math.floor(ys[0]) - support + 1)
        right, bottom = min(sw, math.floor(xs[-1]) + support + 1), min(sh, math.floor(ys[-1]) + support + 1)

    source = read((left, top, right, bottom))
    model_management.throw_exception_if_processing_interrupted()
    if method == "nearest-exact":
        result = source.index_select(1, ys - top).index_select(2, xs - left)
    elif method == "lanczos":
        region = tensor2pil(source)
        resized = region.resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS,
                                box=(x0 * sx - left, y0 * sy - top, x1 * sx - left, y1 * sy - top))
        model_management.throw_exception_if_processing_interrupted()
        result = pil2tensor(resized)
        if result.ndim == 3:
            result = result.unsqueeze(-1)
    elif method == "area":
        if sx.is_integer() and sy.is_integer():
            result = functional.avg_pool2d(source.movedim(-1, 1), (int(sy), int(sx))).movedim(1, -1)
        else:
            # Adaptive average pooling uses floor/ceil bin boundaries. Prefix
            # sums evaluate the same bins without allocating per-pixel windows.
            starts_x = torch.floor(torch.arange(x0, x1, dtype=torch.float64) * sx).long() - left
            ends_x = torch.ceil(torch.arange(x0 + 1, x1 + 1, dtype=torch.float64) * sx).long() - left
            starts_y = torch.floor(torch.arange(y0, y1, dtype=torch.float64) * sy).long() - top
            ends_y = torch.ceil(torch.arange(y0 + 1, y1 + 1, dtype=torch.float64) * sy).long() - top
            sums = functional.pad(source.cumsum(2, dtype=torch.float64), (0, 0, 1, 0))
            rows = (sums[:, :, ends_x] - sums[:, :, starts_x]) / (ends_x - starts_x)[None, None, :, None]
            sums = functional.pad(rows.cumsum(1), (0, 0, 0, 0, 1, 0))
            result = ((sums[:, ends_y] - sums[:, starts_y]) / (ends_y - starts_y)[None, :, None, None]).to(source.dtype)
    else:
        # Global pixel centers preserve interpolation across tile boundaries.
        # Work in pixel coordinates to avoid normalized-grid rounding on large
        # images, while keeping each separable pass bounded and interruptible.
        rows = _interpolate_axis(source, xs, left, 2, method == "bicubic")
        result = _interpolate_axis(rows, ys, top, 1, method == "bicubic")
    model_management.throw_exception_if_processing_interrupted()
    return result.nan_to_num_(nan=0, posinf=1, neginf=0).clamp_(0, 1)


@torch.inference_mode()
def resize_image(image, width, height, method, supersample=1):
    model_management.throw_exception_if_processing_interrupted()
    if image.shape[1:3] == (height, width) and supersample == 1:
        return image
    source_size = image.shape[2], image.shape[1]
    target_size = width, height
    intermediate = width * supersample, height * supersample
    first_method = "bicubic" if method == "area" else method
    # Bound both the supersampled tile and the original filter footprint. No
    # tensor/PIL image with the full supersampled dimensions is ever created.
    tile_x = max(1, min(128, int(1024 / max(supersample, source_size[0] / width))))
    tile_y = max(1, min(128, int(1024 / max(supersample, source_size[1] / height))))
    # Extreme reductions can need a wide source filter even for one output
    # pixel. Budget that footprint as well as the bounded supersampled tile.
    source_width = min(source_size[0], math.ceil((tile_x + 12) * source_size[0] / width) + 12)
    source_height = min(source_size[1], math.ceil((tile_y + 12) * source_size[1] / height) + 12)
    workspace = max(128 * 1024 ** 2, source_width * source_height * image.shape[-1] * 4 * 8)
    check_resize_memory(width, height, image.shape[-1], len(image), workspace)
    output = torch.empty((len(image), height, width, image.shape[-1]), dtype=image.dtype, device="cpu")
    for frame in range(len(image)):
        def source(box, frame=frame):
            x0, y0, x1, y1 = box
            return image[frame:frame + 1, y0:y1, x0:x1]

        def supersampled(box):
            return _region(source, source_size, intermediate, box, first_method)

        for y in range(0, height, tile_y):
            for x in range(0, width, tile_x):
                model_management.throw_exception_if_processing_interrupted()
                box = x, y, min(x + tile_x, width), min(y + tile_y, height)
                tile = _region(supersampled if supersample > 1 else source,
                               intermediate if supersample > 1 else source_size, target_size, box, method)
                output[frame:frame + 1, y:box[3], x:box[2]] = tile
                del tile
    return output
