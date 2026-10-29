# One bounded configuration for the combined image adjustment pipeline.
import copy
import json
from pathlib import Path

import folder_paths

from .image_color_match import COLOR_MATCH_METHODS
from .image_helpers import unwrap_value
from .resolution_sizing import number, require_choice, require_fields, require_number

WIDGET_TYPE = "ECLIPSE_NOVA_IMAGE_ADJUSTMENTS"
OPTIONAL = ("soften", "scale", "color_match", "sharpen")


def choice(label, default, values):
    return {"label": label, "default": default, "choices": values}


GROUPS = {
    "soften": {
        "method": choice("Method", "wavelet", {key: label for key, label in [
            ("gaussian", "Gaussian"), ("bilateral", "Bilateral"), ("wavelet", "Wavelet"),
            ("median", "Median"), ("anisotropic", "Anisotropic"), ("edge_blur", "Edge blur")]}),
        "strength": number("Strength", .5, -1, 1, .01),
        "radius": number("Radius", 1.5, .1, 10, .1),
        "iterations": number("Iterations", 8, 1, 50),
    },
    "scale": {
        "model": {"label": "Upscale model", "default": "", "files": "upscale_models"},
        "target": choice("Target", "factor", {"factor": "Factor", "fixed": "Fixed size", "native": "Native model size"}),
        "factor": number("Factor", 2, .01, 16, .01),
        "width": number("Width", 1024, 1, 48000),
        "height": number("Height", 1024, 1, 48000),
        "resampling": choice("Resampling", "lanczos", {key: key for key in ["nearest-exact", "bilinear", "area", "bicubic", "lanczos"]}),
        "divisor": number("Divisible by", 8, 1, 256),
        "supersample": {"label": "Supersample", "default": False},
        "supersample_factor": choice("Supersample factor", "8", {str(value): f"{value}×" for value in [2, 4, 6, 8]}),
    },
    "color_match": {
        "method": choice("Method", "mkl", {key: key for key in COLOR_MATCH_METHODS}),
        "strength": number("Strength", 1, 0, 10, .01),
        "pairing": choice("Reference pairing", "first", {"first": "First reference for all frames", "frames": "Match frames; repeat last reference"}),
    },
    "color": {
        "brightness": number("Brightness", 0, -1, 1, .01),
        "contrast": number("Contrast", 1, -1, 2, .01),
        "saturation": number("Saturation", 1, 0, 5, .01),
        "temperature": number("Temperature", 0, -1, 1, .01),
        "tint": number("Tint", 0, -1, 1, .01),
        "hue": number("Hue (°)", 0, -180, 180, .1),
    },
    "detail": {
        "sharpness": number("Sharpness", 1, -5, 5, .01),
        "blur": number("Blur passes", 0, 0, 16),
        "gaussian": number("Gaussian radius", 0, 0, 1024, .1),
        "edge": number("Edge enhance", 0, 0, 1, .01),
    },
    "grade": {
        "solarize": number("Solarize threshold", 0, 0, 1, .01),
        "lut": {"label": "LUT file", "default": "", "files": "luts"},
        "strength": number("LUT strength", 1, 0, 1, .01),
    },
    "sharpen": {
        "amount": number("Amount", 5, 0, 25, .5),
        "blend": number("Blend", .5, 0, 1, .01),
        "noise_radius": number("Noise radius", 7, 1, 25),
        "preserve_edges": number("Preserve edges", .75, 0, 1, .01),
    },
    "finish": {
        "vignette": number("Vignette", 0, 0, 1, .01),
        "center_x": number("Center X", .5, 0, 1, .01),
        "center_y": number("Center Y", .5, 0, 1, .01),
        "aberration": number("Chromatic aberration", 0, 0, 1, .01),
        "grain": number("Grain strength", 0, 0, 1, .01),
        "grain_size": number("Grain size", 1, 1, 10, .1),
        "grain_color": number("Grain color", 0, 0, 1, .01),
    },
}
PROCESSING = {"detail_enhance": False, "per_frame": True, "cpu_threads": False}
EXTERNAL_FACTOR = number("Connected upscale_by", 0, 0, 16, .01)


def group_defaults(group):
    return {key: field["default"] for key, field in GROUPS[group].items()}


def default_configuration():
    return {"version": 1, "processing": dict(PROCESSING),
            **{group: None if group in OPTIONAL else group_defaults(group) for group in GROUPS}}


def register_luts():
    if "luts" not in folder_paths.folder_names_and_paths:
        folder_paths.folder_names_and_paths["luts"] = ([str(Path(folder_paths.models_dir) / "luts")], {".cube"})


def editor_spec():
    register_luts()
    return copy.deepcopy({"groups": GROUPS, "optional": OPTIONAL, "processing": PROCESSING,
                          "files": {key: folder_paths.get_filename_list(key) for key in ["luts", "upscale_models"]}})


def selected_path(category, name):
    if category == "luts":
        register_luts()
    path = folder_paths.get_full_path(category, name)
    if not path:
        raise ValueError(f"Selected {category} file is missing: {name}")
    return path


def validate_configuration(raw, *, check_files=True):
    raw = unwrap_value(raw)
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("Image adjustments configuration must be a JSON string of at most 16 KB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid image adjustments configuration JSON.") from error
    require_fields(config, ("version", "processing", *GROUPS))
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 image adjustments configuration.")
    require_fields(config["processing"], PROCESSING, name="Processing options")
    if any(type(value) is not bool for value in config["processing"].values()):
        raise ValueError("Processing options must be enabled or disabled.")
    for group, fields in GROUPS.items():
        values = config[group]
        if group in OPTIONAL and values is None:
            continue
        require_fields(values, fields, name=group.replace("_", " ").title())
        for key, field in fields.items():
            value = values[key]
            if "min" in field:
                require_number(value, field)
            elif "choices" in field:
                require_choice(value, field["choices"], field["label"])
            elif "files" in field:
                if not isinstance(value, str) or len(value) > 1024 or "\x00" in value:
                    raise ValueError(f"{field['label']} must be a local filename.")
                if check_files and value and (group != "grade" or values["strength"] != 0):
                    selected_path(field["files"], value)
            elif type(value) is not bool:
                raise ValueError(f"{field['label']} must be enabled or disabled.")
    return config


def configuration_fingerprint(raw):
    config = validate_configuration(raw, check_files=False)
    if config["finish"]["grain"] > 0:
        return float("nan")
    files = []
    for category, name in [("upscale_models", (config["scale"] or {}).get("model")),
                           ("luts", config["grade"]["lut"] if config["grade"]["strength"] else "")]:
        if name:
            path = selected_path(category, name)
            stat = Path(path).stat()
            files.append((path, stat.st_mtime_ns, stat.st_size))
    return files
