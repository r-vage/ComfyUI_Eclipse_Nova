# Resolution-only PIPE settings shared by image and video workflows.

import copy
import json

from .resolution_sizing import (
    DIMENSIONS,
    SIZING,
    default_image_size,
    number,
    require_fields,
    require_number,
    validate_size,
)

WIDGET_TYPE = "ECLIPSE_NOVA_RESOLUTION_CONFIGURATION"
BATCH_SIZE = number("Batch size", 1, 1, 4096)


def default_configuration():
    return {"version": 1, "size": default_image_size()}


def editor_spec():
    return copy.deepcopy({"dimensions": DIMENSIONS, "sizing": SIZING, "batch_size": BATCH_SIZE})


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > 32768:
        raise ValueError("Resolution configuration must be a JSON string of at most 32 KB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid resolution configuration JSON.") from error
    require_fields(config, ("version", "size"), ("batch_size",))
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 resolution configuration.")
    validate_size(config["size"])
    if "batch_size" in config:
        require_number(config["batch_size"], BATCH_SIZE)
    return config


def resolution_pipe(config):
    pipe = {key: int(config["size"][key]) for key in ("width", "height")}
    if "batch_size" in config:
        pipe["batch_size"] = int(config["batch_size"])
    return pipe
