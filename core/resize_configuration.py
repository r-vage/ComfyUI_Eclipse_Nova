# Structured resize settings: inactive controls live only in workflow editor drafts.

import copy
import json
import re

from .devices import device_selection
from .image_helpers import unwrap_value
from .image_resize import ImageResizeExecution
from .resolution_sizing import number, require_choice, require_fields, require_number

WIDGET_TYPE = "ECLIPSE_NOVA_RESIZE_CONFIGURATION"
CHOICES = {
    "scale_to": {"longest": "Longest", "shortest": "Shortest", "width": "Width",
                 "height": "Height", "total_pixels": "Pixels", "custom": "Custom"},
    "aspect_ratio": {key: key if key != "original" else "Original" for key in
                     ("original", "1:1", "3:2", "4:3", "16:9", "2:3", "3:4", "9:16")},
    "fit": {"resize": "Keep ratio", "crop": "Crop", "pad": "Solid padding",
            "pad_edge": "Edge color", "pad_edge_pixel": "Edge pixels",
            "pillarbox_blur": "Blurred background", "stretch": "Stretch"},
    "crop_position": {key: key.title() for key in ("center", "top", "bottom", "left", "right")},
    "method": {key: key.title() for key in ("nearest-exact", "bilinear", "area", "bicubic", "lanczos")},
    "device": {"default": "Default", "cpu": "CPU"},
}
NUMBERS = {
    "size": number("Size", 1024, 1, 16384),
    "custom_width": number("Width", 512, 0, 16384),
    "custom_height": number("Height", 512, 0, 16384),
    "divisible_by": number("Divisible by", 16, 1, 512),
}
DEFAULTS = {"scale_to": "longest", "size": 1024, "custom_width": 512,
            "custom_height": 512, "aspect_ratio": "original", "fit": "resize",
            "crop_position": "center", "pad_color": "#000000", "method": "lanczos",
            "divisible_by": 16, "device": "cpu", "use_input_size": True}


def active_fields(config):
    fields = ["scale_to", "fit", "method", "divisible_by", "device", "use_input_size"]
    fields += ["custom_width", "custom_height"] if config["scale_to"] == "custom" else ["size", "aspect_ratio"]
    if config["fit"] not in ("resize", "stretch"):
        fields.append("crop_position")
    if config["fit"] == "pad":
        fields.append("pad_color")
    return fields


def default_configuration():
    return {"version": 1, **{key: DEFAULTS[key] for key in active_fields(DEFAULTS)}}


def editor_spec():
    return copy.deepcopy({"defaults": DEFAULTS, "choices": CHOICES, "numbers": NUMBERS})


def validate_configuration(raw):
    raw = unwrap_value(raw)
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("Resize configuration must be a JSON string of at most 16 KB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid resize configuration JSON.") from error
    require_fields(config, ("version", "scale_to", "fit"), tuple(DEFAULTS))
    config.setdefault("use_input_size", True)
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 resize configuration.")
    require_choice(config["scale_to"], CHOICES["scale_to"], "Scale to")
    require_choice(config["fit"], CHOICES["fit"], "Fit")
    require_fields(config, ["version", *active_fields(config)])
    config['device'] = device_selection(config['device'])
    for key in active_fields(config):
        if key in CHOICES:
            require_choice(config[key], CHOICES[key], key.replace("_", " ").title())
        elif key in NUMBERS:
            require_number(config[key], NUMBERS[key])
        elif key == "use_input_size" and type(config[key]) is not bool:
            raise ValueError("Use inputs must be enabled or disabled.")
        elif key == "pad_color" and (not isinstance(config[key], str) or not re.fullmatch(r"#?(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", config[key])):
            raise ValueError("Padding color must be a hex color such as #000000 or #fff.")
    return config


def execute_configuration(image, configuration, mask=None, width=None, height=None):
    config = validate_configuration(configuration)
    dimensions = {}
    for key, value in (("width", width), ("height", height)):
        value = unwrap_value(value) if config["use_input_size"] else None
        if value is not None:
            require_number(value, NUMBERS[f"custom_{key}"])
            value = int(value)
        dimensions[f"{key}_override"] = value
    settings = {**DEFAULTS, **config}
    settings.pop("version")
    settings.pop("use_input_size")
    for key in NUMBERS:
        settings[key] = int(settings[key])
    return ImageResizeExecution.execute(image, mask=mask, **settings, **dimensions)
