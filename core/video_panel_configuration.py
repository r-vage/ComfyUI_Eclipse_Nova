# Contracts for video loader and preview panels; connected values override local fields.

import json

from .resolution_sizing import number, require_choice, require_fields, require_number
from .video_loader import parse_playlist

LOAD_WIDGET = "ECLIPSE_NOVA_LOAD_VIDEO"
PREVIEW_WIDGET = "ECLIPSE_NOVA_PREVIEW_VIDEO"
SIZE = number("Size", 0, 0, 16384)
FPS = number("FPS", 24.0, 1.0, 240.0, 0.01)
PREVIEW_FPS = number("FPS", 16.0, 1.0, 120.0, 0.01)


def default_load():
    return {"version": 1, "clips": [], "width": 0, "height": 0,
            "fit": "pad", "timing_mode": "source", "fps": 24.0}


def default_preview():
    return {"version": 1, "fps": 16.0, "stop": False}


def _parse(raw, fields):
    if not isinstance(raw, str) or len(raw) > 262144:
        raise ValueError("Video configuration must be JSON text smaller than 256 KiB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid video configuration JSON.") from error
    require_fields(config, fields)
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 video configuration.")
    return config


def validate_load(raw):
    config = _parse(raw, default_load())
    config["clips"] = parse_playlist(json.dumps({"version": 1, "clips": config["clips"]}), allow_empty=True)
    for key in ("width", "height"):
        require_number(config[key], SIZE)
    require_number(config["fps"], FPS)
    require_choice(config["fit"], ("pad", "crop", "stretch"), "Fit")
    require_choice(config["timing_mode"], ("source", "fixed"), "Timing")
    return config


def validate_preview(raw):
    config = _parse(raw, default_preview())
    require_number(config["fps"], PREVIEW_FPS)
    if type(config["stop"]) is not bool:
        raise ValueError("Stop must be enabled or disabled.")
    return config


def playlist_value(config):
    # Empty slots remain in workflows, but never reach decoding or preview jobs.
    return json.dumps({"version": 1, "clips": [row for row in config["clips"] if row["file"] is not None]})


def resolve_load(config, width=None, height=None, fps=None):
    result = {key: config[key] for key in ("width", "height", "fps", "fit", "timing_mode")}
    for key, value, field in (("width", width, SIZE), ("height", height, SIZE), ("fps", fps, FPS)):
        if value is not None:
            result[key] = require_number(value, field)
    # JSON may contain 640.0, while the video engine deliberately accepts ints.
    result["width"], result["height"] = int(result["width"]), int(result["height"])
    return result
