# Ordered RGB finishing pipeline with separate alpha and bounded CPU concurrency.
import math
import os
from concurrent.futures import ThreadPoolExecutor

import torch
from comfy import model_management, utils
from PIL import Image, ImageEnhance, ImageFilter

from . import image_adjustment_effects as effects
from .image_adjustments_configuration import (
    EXTERNAL_FACTOR,
    selected_path,
    validate_configuration,
)
from .image_color_match import CPU_METHODS, match_color, sanitize
from .image_helpers import (
    flatten_images,
    pil2tensor,
    prepare_image_output,
    tensor2pil,
    unwrap_value,
    was_input_batch,
)
from .image_resampling import check_resize_memory, resize_image
from .image_soften import _pad, soften
from .resolution_sizing import require_number


def target_dimensions(original, settings, external=None):
    if external is not None:
        if external == 0:
            return None
        values = [value * external for value in original]
    elif settings["target"] == "native":
        return None
    elif settings["target"] == "factor":
        values = [value * settings["factor"] for value in original]
    else:
        values = [settings["width"], settings["height"]]
    divisor = int(settings["divisor"])
    # Nearest multiple, ties round up; never produce zero-sized images.
    result = tuple(max(1, math.floor(value / divisor + .5)) * divisor for value in values)
    if max(result) > 48000:
        raise ValueError("Scaled dimensions exceed 48000 pixels per edge.")
    return result


def resample(image, width, height, method):
    return resize_image(image, width, height, method)


def scale_image(rgb, alpha, settings, external, backend):
    target = target_dimensions((rgb.shape[2], rgb.shape[1]), settings, external)
    if backend is not None:
        check_resize_memory(rgb.shape[2] * backend.scale, rgb.shape[1] * backend.scale, batch=len(rgb))
        rgb = sanitize(backend.upscale(rgb))
        model_management.throw_exception_if_processing_interrupted()
    if target is not None:
        width, height = target
        if settings["supersample"]:
            factor = int(settings["supersample_factor"])
            rgb = resize_image(rgb, width, height, settings["resampling"], supersample=factor)
        else:
            rgb = resample(rgb, width, height, settings["resampling"])
    if alpha is not None:
        alpha = resample(alpha, rgb.shape[2], rgb.shape[1], settings["resampling"])
    return rgb, alpha


def color_and_detail(rgb, color, detail, detail_enhance):
    if color["brightness"] != 0:
        rgb = (rgb + color["brightness"]).clamp(0, 1)
    if color["contrast"] != 1:
        rgb = (rgb * color["contrast"]).clamp(0, 1)
    if color["saturation"] != 1:
        rgb = pil2tensor(ImageEnhance.Color(tensor2pil(rgb)).enhance(color["saturation"]))
    rgb = effects.adjust_temperature_and_tint(rgb, color["temperature"], color["tint"])
    rgb = effects.adjust_hue(rgb, color["hue"])
    if (detail["sharpness"] == 1 and not any(detail[key] for key in ("blur", "gaussian", "edge")) and not detail_enhance):
        return rgb
    pil = tensor2pil(rgb)
    if detail["sharpness"] != 1:
        pil = ImageEnhance.Sharpness(pil).enhance(detail["sharpness"])
    for _ in range(int(detail["blur"])):
        model_management.throw_exception_if_processing_interrupted()
        pil = pil.filter(ImageFilter.BLUR)
    if detail["gaussian"]:
        pil = pil.filter(ImageFilter.GaussianBlur(detail["gaussian"]))
    if detail["edge"]:
        pil = Image.blend(pil, pil.filter(ImageFilter.EDGE_ENHANCE_MORE), detail["edge"])
    if detail_enhance:
        pil = pil.filter(ImageFilter.DETAIL)
    return pil2tensor(pil)


def smart_sharpen(rgb, settings):
    import cv2
    import kornia

    image = rgb[0]
    radius, edges = int(settings["noise_radius"]), settings["preserve_edges"]
    edges = max(1 - edges, .05) if edges > 0 else edges
    blurred = torch.from_numpy(cv2.bilateralFilter(image.numpy(), radius, edges, .3 * ((radius - 1) * .5 - 1) + .8)) if radius > 1 else image
    sharpened = image
    if settings["amount"] > 0:
        original = image.movedim(-1, 0).unsqueeze(0)
        # Kornia's 3x3 sharpness kernel also supports 1px inputs after padding.
        padded = _pad(original, (0, max(0, 3 - image.shape[1]), 0, max(0, 3 - image.shape[0])))
        sharpened = kornia.enhance.sharpness(padded, settings["amount"])[0, :, :image.shape[0], :image.shape[1]].movedim(0, -1)
    return torch.lerp(blurred, sharpened, settings["blend"]).clamp(0, 1).unsqueeze(0)


def _check_images(images, label):
    if not images:
        raise ValueError(f"{label}: no images provided.")
    if any(item.ndim != 4 or min(item.shape) < 1 or item.shape[-1] not in (1, 3, 4) for item in images):
        raise ValueError(f"{label}: expected non-empty BHWC images with 1, 3 or 4 channels.")


def _rgb(image):
    rgb = image[..., :3].detach().cpu().float()
    return sanitize(rgb.expand(-1, -1, -1, 3) if rgb.shape[-1] == 1 else rgb)


def _model_backend(path, frames):
    from .video_upscale import PyTorchUpscaler

    return PyTorchUpscaler(path, max(frame.shape[2] for frame in frames), max(frame.shape[1] for frame in frames), 1, "auto", 512)


@torch.inference_mode()
def execute_configuration(image, raw, image_ref=None, upscale_by=None):
    model_management.throw_exception_if_processing_interrupted()
    config = validate_configuration(raw)
    frames = flatten_images(image)
    _check_images(frames, "Image adjustments")
    scale, match = config["scale"], config["color_match"]
    external = unwrap_value(upscale_by) if scale else None
    if external is not None:
        require_number(external, EXTERNAL_FACTOR)
    references = flatten_images(image_ref) if match and match["strength"] else []
    if match and match["strength"]:
        _check_images(references, "Color match reference")
    lut = effects.load_lut(selected_path("luts", config["grade"]["lut"])) if config["grade"]["lut"] and config["grade"]["strength"] else None
    backend = None
    progress = utils.ProgressBar(len(frames) * 7)
    done = 0

    @torch.inference_mode()
    def stage(item, index):
        frame_index, rgb, alpha = item
        model_management.throw_exception_if_processing_interrupted()
        if index == 0 and config["soften"]:
            rgb = soften(rgb, config["soften"])
        elif index == 1 and scale:
            rgb, alpha = scale_image(rgb, alpha, scale, external, backend)
        elif index == 2 and match and match["strength"]:
            ref = references[min(frame_index, len(references) - 1)] if match["pairing"] == "frames" else references[0]
            rgb = match_color(rgb, _rgb(ref), match["method"], match["strength"])
        elif index == 3:
            rgb = color_and_detail(rgb, config["color"], config["detail"], config["processing"]["detail_enhance"])
        elif index == 4:
            rgb = effects.apply_solarize(rgb, config["grade"]["solarize"])
            if lut is not None:
                rgb = effects.apply_lut(rgb, lut, config["grade"]["strength"])
        elif index == 5 and config["sharpen"]:
            rgb = smart_sharpen(rgb, config["sharpen"])
        elif index == 6:
            finish = config["finish"]
            rgb = effects.apply_vignette(rgb, finish["vignette"], finish["center_x"], finish["center_y"])
            rgb = effects.apply_chromatic_aberration(rgb, finish["aberration"])
            rgb = effects.apply_film_grain(rgb, finish["grain"], finish["grain_size"], finish["grain_color"])
        return frame_index, rgb, alpha

    def prepare(index):
        frame = frames[index]
        return index, _rgb(frame), frame[..., 3:4].detach().cpu().float() if frame.shape[-1] == 4 else None

    def advance(count):
        nonlocal done
        done += count
        progress.update_absolute(done)

    def finish(item):
        _, rgb, alpha = item
        return torch.cat((rgb, alpha), dim=-1) if alpha is not None else rgb

    try:
        if scale:
            # Validate final dimensions before loading a model or allocating its output.
            for frame in frames:
                target = target_dimensions((frame.shape[2], frame.shape[1]), scale, external)
                if target is not None:
                    check_resize_memory(*target, channels=frame.shape[-1])
            if scale["model"]:
                backend = _model_backend(selected_path("upscale_models", scale["model"]), frames)
        if config["processing"]["per_frame"]:
            output = []
            for frame_index in range(len(frames)):
                item = prepare(frame_index)
                for index in range(7):
                    item = stage(item, index)
                    advance(1)
                output.append(finish(item))
        else:
            items = [prepare(index) for index in range(len(frames))]
            workers = min(len(frames), os.cpu_count() or 1, 4) if config["processing"]["cpu_threads"] else 1
            # GPU/model stages remain serial. Only independent CPU work is parallel.
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for index in range(7):
                    if workers > 1 and (index in (3, 5) or (index == 2 and match and match["method"] in CPU_METHODS)):
                        items = list(pool.map(lambda item, index=index: stage(item, index), items))
                    else:
                        items = [stage(item, index) for item in items]
                    advance(len(items))
            output = [finish(item) for item in items]
    finally:
        if backend is not None:
            backend.close()
    if was_input_batch(image) and all(frame.shape[1:] == output[0].shape[1:] for frame in output):
        return prepare_image_output(torch.cat(output), True)
    return output
