# Small, strict contracts for the selector and comparer panels.

import json

from .image_helpers import unwrap_value

WIDGET_TYPE = "ECLIPSE_NOVA_IMAGE_REVIEW"
DEFAULTS = {
    "selector": {"version": 1, "auto_confirm": False, "trigger": 0},
    "comparer": {"version": 1, "output": "b"},
}


def default_configuration(kind):
    return json.dumps(DEFAULTS[kind])


def validate_configuration(raw, kind):
    raw = unwrap_value(raw)
    if not isinstance(raw, str) or len(raw) > 2048:
        raise ValueError("Image review configuration must be a JSON string of at most 2 KB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid image review configuration JSON.") from error
    if not isinstance(config, dict) or config.keys() != DEFAULTS[kind].keys():
        raise ValueError("Image review configuration has missing or unsupported fields.")
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 image review configuration.")
    if kind == "selector":
        if type(config["auto_confirm"]) is not bool:
            raise ValueError("Auto confirm must be true or false.")
        if type(config["trigger"]) is not int or not 0 <= config["trigger"] <= 2147483647:
            raise ValueError("Invalid selection execution counter.")
    elif config["output"] not in ("a", "b"):
        raise ValueError("Choose output A or B.")
    return config
