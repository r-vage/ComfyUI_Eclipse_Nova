# Configuration contracts for the two image-source panels.

import copy
import json

from .image_metadata import GENERATION_GROUPS
from .resize_configuration import default_configuration as default_resize
from .resize_configuration import editor_spec as resize_spec
from .resize_configuration import validate_configuration as validate_resize
from .resolution_sizing import number, require_choice, require_fields, require_number

IMAGE_WIDGET = "ECLIPSE_NOVA_LOAD_IMAGE"
FILES_WIDGET = "ECLIPSE_NOVA_LOAD_FILES"
CHOICES = {
    "mode": {"single": "Single", "range": "Range", "step": "Step"},
    "advance": {"fixed": "Fixed", "next": "Next", "previous": "Previous", "random": "Random", "shuffle": "Shuffle"},
    "step_advance": {"fixed": "Fixed", "next": "Increment", "previous": "Decrement", "random": "Random"},
    "sort_by": {"name": "Name", "date_modified": "Modified date", "date_created": "Created / changed date", "size": "File size"},
    "sort_order": {"ascending": "Ascending", "descending": "Descending"},
    "resize_policy": {"first": "Match first", "largest": "Match largest", "smallest": "Match smallest", "strict": "Require same size", "custom": "Custom"},
}
INDEX = number("Index", 0, -2147483647, 2147483647)


def default_image():
    return {"version": 1, "source": "input", "files": {"input": "", "output": ""}, "metadata": False,
            "metadata_fields": dict.fromkeys(GENERATION_GROUPS, True)}


def default_files():
    return {"version": 1, "paths": "", "mode": "single", "recursive": False,
            "metadata": False, "stop_at_end": True, "revision": 0,
            "sort": {"by": "name", "order": "ascending"},
            "single": {"index": 0, "advance": "fixed"}, "range": {"start": 0, "end": -1},
            "step": {"batch_index": 0, "advance": "fixed"}, "resize": None}


def editor_spec(kind):
    return copy.deepcopy({"kind": kind, "choices": CHOICES, "index": INDEX,
                          "resize": resize_spec(), "resize_default": {"policy": "first", "settings": default_resize()}})


def _parse(raw):
    if not isinstance(raw, str) or len(raw) > 65536:
        raise ValueError("Loader configuration must be a JSON string of at most 64 KB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid loader configuration JSON.") from error
    if not isinstance(config, dict) or type(config.get("version")) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 loader configuration.")
    return config


def validate_image(raw):
    config = _parse(raw)
    config.setdefault("metadata_fields", dict.fromkeys(GENERATION_GROUPS, True))
    require_fields(config, default_image())
    require_choice(config["source"], ("input", "output"), "Source")
    require_fields(config["files"], ("input", "output"), name="Files")
    for filename in config["files"].values():
        if not isinstance(filename, str) or len(filename) > 4096 or "\x00" in filename:
            raise ValueError("Invalid image filename.")
    if type(config["metadata"]) is not bool:
        raise ValueError("Metadata must be enabled or disabled.")
    require_fields(config["metadata_fields"], GENERATION_GROUPS, name="Metadata selection")
    if any(type(value) is not bool for value in config["metadata_fields"].values()):
        raise ValueError("Metadata groups must be enabled or disabled.")
    return config


def validate_files(raw):
    config = _parse(raw)
    require_fields(config, default_files())
    if not isinstance(config["paths"], str) or len(config["paths"]) > 32768 or "\x00" in config["paths"]:
        raise ValueError("Paths must be text of at most 32 KB.")
    for key in ("recursive", "metadata", "stop_at_end"):
        if type(config[key]) is not bool:
            raise ValueError(f"{key} must be enabled or disabled.")
    require_number(config["revision"], number("Revision", 0, 0, 2**53 - 1))
    require_choice(config["mode"], CHOICES["mode"], "Selection")
    require_fields(config["sort"], ("by", "order"), name="Sorting")
    require_choice(config["sort"]["by"], CHOICES["sort_by"], "Sort by")
    require_choice(config["sort"]["order"], CHOICES["sort_order"], "Sort order")
    for key, fields in (("single", ("index", "advance")), ("range", ("start", "end")), ("step", ("batch_index", "advance"))):
        require_fields(config[key], fields, name=key.title())
        if key == config["mode"] or key == "range" and config["mode"] == "step":
            for field in fields:
                if field == "advance":
                    require_choice(config[key][field], CHOICES["step_advance" if key == "step" else "advance"], "After run")
                else:
                    require_number(config[key][field], INDEX)
    if config["resize"] is not None:
        require_fields(config["resize"], ("policy", "settings"), name="Resize")
        require_choice(config["resize"]["policy"], CHOICES["resize_policy"], "Size policy")
        if config["resize"]["policy"] == "custom":
            validate_resize(json.dumps(config["resize"]["settings"]))
    return config
