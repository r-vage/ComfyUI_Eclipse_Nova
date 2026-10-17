# Explicit contracts for conversion, mask cropping and system recording panels.
import copy
import json
import re

from .image_conversion import _STYLE_OPTIONS
from .image_crop_by_mask import (
    DEVICE_OPTIONS,
    DIVISIBILITY_OPTIONS,
    MIRROR_OPTIONS,
    RESCALE_ALGORITHMS,
)
from .resolution_sizing import number, require_choice, require_fields, require_number
from .system_audio import SystemAudioError, _processing_config

WIDGET_TYPE = "ECLIPSE_NOVA_MEDIA_TOOL"
TITLES = {"convert": "Image Convert", "crop": "Image Crop by Mask", "recorder": "System Audio Recorder"}
DEFAULTS = {
    "convert": {"to_rgb": False, "to_grayscale": False, "composite_alpha": False,
                "background_color": "#000000", "style": "none"},
    "crop": {"rotation": 0, "mirror": "none", "mask_blur": 0, "mask_threshold": 0.1,
             "context_expand": 1.0, "target_width": 512, "target_height": 512,
             "divisible_by": "32", "rescale_algorithm": "bicubic", "device": "auto"},
    "recorder": {"filename_prefix": "audio/system_recording", "format": "wav", "mp3_bitrate": "320 kbps",
                 "output_device": "default", "strip_start_silence": True, "silence_threshold_db": -70.0},
}
NUMBERS = {
    "convert": {},
    "crop": {"rotation": number("Rotation", 0, -180, 180), "mask_blur": number("Mask blur", 0, 0, 512),
             "mask_threshold": number("Threshold", .1, 0, 1, .01), "context_expand": number("Zoom", 1, .1, 4, .05),
             "target_width": number("Width", 512, 64, 16384), "target_height": number("Height", 512, 64, 16384)},
    "recorder": {"silence_threshold_db": number("Threshold (dBFS)", -70, -96, -20, .1)},
}
CHOICES = {
    "convert": {"style": _STYLE_OPTIONS},
    "crop": {"mirror": MIRROR_OPTIONS, "divisible_by": DIVISIBILITY_OPTIONS,
             "rescale_algorithm": RESCALE_ALGORITHMS, "device": DEVICE_OPTIONS},
    "recorder": {"format": ["wav", "wav + mp3", "mp3"],
                 "mp3_bitrate": ["128 kbps", "192 kbps", "256 kbps", "320 kbps"]},
}
TOGGLES = {"convert": {"to_rgb": "RGB", "to_grayscale": "Grayscale", "composite_alpha": "Composite alpha"},
           "crop": {}, "recorder": {"strip_start_silence": "Trim silence"}}


def default_configuration(kind):
    config = {"version": 1, "kind": kind, "parameters": copy.deepcopy(DEFAULTS[kind])}
    if kind == "recorder":
        config["recording_token"] = ""
    return config


def editor_spec(kind):
    return {"kind": kind, "title": TITLES[kind], "defaults": DEFAULTS[kind], "numbers": NUMBERS[kind],
            "choices": CHOICES[kind], "toggles": TOGGLES[kind]}


def validate_configuration(raw, kind):
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("Configuration must be JSON text smaller than 16 KiB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid configuration JSON.") from error
    require_fields(config, default_configuration(kind))
    if type(config["version"]) is not int or config["version"] != 1 or config["kind"] != kind:
        raise ValueError(f"Expected version 1 {TITLES[kind]} configuration.")
    params = config["parameters"]
    require_fields(params, DEFAULTS[kind], name="Parameters")
    for key, field in NUMBERS[kind].items():
        require_number(params[key], field)
    for key, choices in CHOICES[kind].items():
        require_choice(params[key], choices, key.replace("_", " ").capitalize())
    for key in TOGGLES[kind]:
        if type(params[key]) is not bool:
            raise ValueError(f"{key} must be enabled or disabled.")
    if kind == "convert":
        color = params["background_color"]
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Background color must be #RRGGBB.")
    elif kind == "recorder":
        for key, value, limit in (("Output device", params["output_device"], 128),
                                  ("Recording token", config["recording_token"], 128)):
            if not isinstance(value, str) or len(value) > limit or "\0" in value:
                raise ValueError(f"Invalid {key.lower()}.")
        if not params["output_device"]:
            raise ValueError("Select an output device.")
        try:
            _processing_config(filename_prefix=params["filename_prefix"], output_format=params["format"],
                               bitrate=params["mp3_bitrate"], strip_start_silence=params["strip_start_silence"],
                               silence_threshold_db=params["silence_threshold_db"])
        except SystemAudioError as error:
            raise ValueError(str(error)) from error
    return config


def crop_parameters(config, target_width=None, target_height=None):
    params = dict(config["parameters"])
    for key, value in (("target_width", target_width), ("target_height", target_height)):
        if value is not None:
            params[key] = require_number(value, NUMBERS["crop"][key])
    # Accept integral JSON numbers while providing integer tensor dimensions.
    for key in ("target_width", "target_height", "rotation", "mask_blur"):
        params[key] = int(params[key])
    return params
