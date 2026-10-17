# Shared comparison previews; original tensors pass through without resizing.

import json
import os
import random
import time

import folder_paths
import torch
from comfy_api.latest import io
from PIL.PngImagePlugin import PngInfo

from .image_helpers import flatten_images, tensor2pil

_PREFIX_APPEND = "_imgcmp_" + "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(5))
_COMPRESS_LEVEL = 1


def _save_images_to_temp(image_list, side, metadata=None):
    # Save image tensor in list to temp folder and return metadata list for UI.
    results = []
    if not image_list:
        return results

    first_img = image_list[0]
    output_dir = folder_paths.get_temp_directory()
    filename_prefix = f"EclipseCompare{side}" + _PREFIX_APPEND
    full_output_folder, filename, counter, subfolder, _ = (
        folder_paths.get_save_image_path(
            filename_prefix, output_dir, first_img.shape[2], first_img.shape[1]
        )
    )

    for batch_number, image in enumerate(image_list):
        img = tensor2pil(image)

        filename_with_batch_num = filename.replace("%batch_num%", str(batch_number))
        timestamp = int(time.time() * 1000) % 100000000
        file = f"{filename_with_batch_num}_{counter:05}_{timestamp}_.png"
        img.save(
            os.path.join(full_output_folder, file),
            pnginfo=metadata,
            compress_level=_COMPRESS_LEVEL,
        )

        results.append({"filename": file, "subfolder": subfolder, "type": "temp"})
        counter += 1

    return results


def _original_tensors(value):
    if isinstance(value, torch.Tensor):
        return [value]
    if isinstance(value, (list, tuple)):
        return [tensor for item in value for tensor in _original_tensors(item)]
    return []


def compare_images(image_a=None, image_b=None, *, default_side="b", prompt=None, extra_pnginfo=None):
    metadata = PngInfo()
    if prompt is not None:
        metadata.add_text("prompt", json.dumps(prompt))
    if extra_pnginfo is not None:
        for key, value in extra_pnginfo.items():
            metadata.add_text(key, json.dumps(value))
    ui = {
        "a_images": _save_images_to_temp(flatten_images(image_a), "A", metadata),
        "b_images": _save_images_to_temp(flatten_images(image_b), "B", metadata),
    }
    first, second = (image_a, image_b) if default_side == "a" else (image_b, image_a)
    output = _original_tensors(first) or _original_tensors(second)
    if not output:
        output = [torch.zeros((1, 64, 64, 3), dtype=torch.float32)]
    return io.NodeOutput(output, ui=ui)
