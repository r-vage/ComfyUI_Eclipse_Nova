# Named sampling recipes; model objects and execution-local controls stay in the node.

import json
import re
import uuid
from pathlib import Path

from .json_store import locked_path, read_json_object, update_json_object
from .sampler_configuration import (
    PRESET_LOCAL_PARAMETERS,
    default_configuration,
    editor_spec,
    validate_configuration,
)

PRESET_ROOT = Path(__file__).resolve().parent.parent / "presets" / "samplers"
MAX_PRESET_BYTES = 32768


def validate_preset(document):
    if (not isinstance(document, dict) or set(document) != {"version", "profile", "parameters"}
            or type(document["version"]) is not int or document["version"] != 1
            or document["profile"] != "advanced"):
        raise ValueError("Expected a version 1 Advanced Sampler preset.")
    fields = editor_spec("advanced")["fields"]
    allowed = fields.keys() - PRESET_LOCAL_PARAMETERS
    required = {key for key in allowed if not fields[key].get("optional")}
    parameters = document["parameters"]
    if not isinstance(parameters, dict) or parameters.keys() - allowed or required - parameters.keys():
        raise ValueError("Preset contains unknown, local-only, or missing sampling settings.")
    config = default_configuration("advanced")
    config["parameters"].update(parameters)
    validated = validate_configuration(json.dumps(config), "advanced")
    return {"version": 1, "profile": "advanced", "parameters": {
        key: value for key, value in validated["parameters"].items() if key in allowed
    }}


def _valid_name(name):
    return (isinstance(name, str) and 0 < len(name) <= 128 and name == name.strip()
            and name not in {".", ".."} and not name.startswith(".")
            and not name.endswith(".") and not re.search(r'[\x00-\x1f\x7f/\\:*?"<>|]', name)
            and name.split(".", 1)[0].upper() not in {
                "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10)),
            })


def _root(*, create=False):
    for directory in (PRESET_ROOT.parent, PRESET_ROOT):
        if directory.is_symlink():
            raise ValueError("Sampler preset folders must not be symlinks.")
        if directory.exists() and not directory.is_dir():
            raise ValueError("Sampler preset path must be a folder.")
    if create:
        PRESET_ROOT.mkdir(parents=True, exist_ok=True)
    return PRESET_ROOT


def _path(name, *, create=False):
    if not _valid_name(name):
        raise ValueError("Use a preset name of 1-128 characters without path separators or reserved filename characters.")
    path = _root(create=create) / f"{name}.json"
    if path.is_symlink():
        raise ValueError("Sampler preset files must not be symlinks.")
    return path


def list_presets():
    root = _root()
    if not root.exists():
        return []
    return sorted((path.stem for path in root.iterdir() if path.suffix == ".json"
                   and _valid_name(path.stem) and not path.is_symlink() and path.is_file()), key=str.casefold)


def load_preset(name):
    path = _path(name)
    if not path.is_file():
        raise FileNotFoundError("Sampler preset does not exist.")
    if path.stat().st_size > MAX_PRESET_BYTES:
        raise ValueError("Sampler preset exceeds the size limit.")
    return validate_preset(read_json_object(path))


def save_preset(name, document, *, overwrite=False):
    if type(overwrite) is not bool:
        raise ValueError("Overwrite must be enabled or disabled.")
    validated = validate_preset(document)
    path = _path(name, create=True)
    if path.exists() and path.stat().st_size > MAX_PRESET_BYTES:
        raise ValueError("Existing sampler preset exceeds the size limit.")
    missing = {"_new_preset": uuid.uuid4().hex}

    def replace(current):
        if _path(name) != path:
            raise ValueError("Sampler preset path changed while saving.")
        if current != missing:
            validate_preset(current)
            if not overwrite:
                raise FileExistsError("Preset already exists; choose another name or enable overwrite.")
        current.clear()
        current.update(validated)

    update_json_object(path, replace, default=missing)


def delete_preset(name):
    path = _path(name)

    def identity():
        info = path.stat()
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    original = identity()
    load_preset(name)
    with locked_path(path):
        if _path(name) != path or identity() != original:
            raise ValueError("Sampler preset changed while preparing deletion.")
        path.unlink()
