# Structured Smart Folder configuration and the existing dictionary PIPE contract.

import copy
import json
import os
import re
import secrets
from datetime import datetime, timezone
from string import Formatter

from .path_helpers import normalize_relative_folder_path
from .resolution_sizing import (
    DIMENSIONS,
    SIZING,
    default_image_size,
    number,
    validate_size,
)
from .resolution_sizing import (
    require_choice as _choice,
)
from .resolution_sizing import (
    require_fields as _object,
)
from .resolution_sizing import (
    require_number as _number,
)

WIDGET_TYPE = "ECLIPSE_NOVA_FOLDER_CONFIGURATION"
MAX_COUNTER = 2**64 - 1


FIELDS = {
    "batch_size": number("Batch size", 1, 1, 4096),
    "frame_rate": number("Frame rate", 30, 8, 240, 0.1),
    "duration": number("Duration (seconds)", 15, 0.5, 180, 0.5),
    "frame_load_cap": number("Frame load cap", 162, 0, 32768),
    "context_length": number("Context length", 81, 1, 32768),
    "loop_count": number("Loop count", 0, 0, 32768),
    "overlap": number("Overlap", 0, 0, 32768),
    "skip_first_frames": number("Skip first frames", 0, 0, 4096),
    "select_every_nth": number("Select every nth", 1, 1, 100),
}


def default_configuration():
    return {"version": 1, "mode": "image", "folder": {"root": "images", "date_time": {
        "format": "%Y-%m-%d", "position": "postfix"}}, "batch_size": 1}


def editor_spec():
    return copy.deepcopy({
        "fields": FIELDS, "dimensions": DIMENSIONS, "sizing": SIZING,
        "defaults": {
            "date_time": {"format": "%Y-%m-%d", "position": "postfix"},
            "batch": {"name": "batch_{}", "number": "1", "policy": "fixed"},
            "image_size": default_image_size(),
            "video_size": {"width": 576, "height": 1024, "sizing": {"mode": "fixed", "divisor": 32}},
            "video": {"frame_rate": 30, "context_length": 81},
            "vhs": {"frame_load_cap": 162, "skip_first_frames": 0, "select_every_nth": 1,
                    "skip_count": "0", "skip_policy": "fixed"},
            "loop": {"loop_count": 0, "overlap": 0},
            "context_length": 81, "duration": 15, "seed": {"value": "0", "policy": "fixed"},
        },
    })


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 1024 or "\x00" in value:
        raise ValueError(f"{label} must contain 1–1024 characters without null bytes.")


def _counter(value, label, minimum=0):
    if (not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,19}", value)
            or not minimum <= int(value) <= MAX_COUNTER):
        raise ValueError(f"{label} must be a decimal integer between {minimum} and {MAX_COUNTER}.")


def format_batch(name, value):
    # Bound formatting widths before formatting; support {}, {0} and {0:03d}.
    _text(name, "Batch folder name")
    try:
        for _literal, field, spec, conversion in Formatter().parse(name):
            if field is None:
                continue
            if field not in ("", "0") or conversion or (spec and not re.fullmatch(r"0?[1-9][0-9]?d", spec)):
                raise ValueError("unsupported placeholder")
        result = name.format(int(value))
    except (IndexError, KeyError, ValueError) as error:
        raise ValueError("Batch folder name: use {}, {0} or {0:03d} for the batch number.") from error
    _text(result, "Formatted batch folder")
    return normalize_relative_folder_path(result)


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > 32768:
        raise ValueError("Smart Folder configuration must be a JSON string of at most 32 KB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid Smart Folder configuration JSON.") from error
    _object(config, ("version", "mode", "folder", "batch_size"), ("size", "video", "seed"))
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 Smart Folder configuration.")
    _choice(config["mode"], ("image", "video"), "Mode")
    _number(config["batch_size"], FIELDS["batch_size"])
    folder = config["folder"]
    _object(folder, ("root",), ("date_time", "batch"), "Output folder")
    _text(folder["root"], "Root folder")
    if "date_time" in folder:
        date = folder["date_time"]
        _object(date, ("format", "position"), name="Date/time")
        _text(date["format"], "Date/time format")
        _choice(date["position"], ("prefix", "postfix"), "Date/time position")
    if "batch" in folder:
        batch = folder["batch"]
        _object(batch, ("name", "number", "policy"), name="Batch folder")
        _counter(batch["number"], "Batch number", 1)
        _choice(batch["policy"], ("fixed", "increment"), "Batch queue policy")
        format_batch(batch["name"], batch["number"])
    if "size" in config:
        size = config["size"]
        # Discard the removed selector without changing saved dimensions.
        if isinstance(size, dict):
            size.pop("latent_type", None)
        validate_size(size)
    if config["mode"] == "image" and "video" in config:
        raise ValueError("Image mode cannot include video settings.")
    if config["mode"] == "video":
        video = config.get("video")
        _object(video, ("frame_rate",), ("context_length", "duration", "vhs", "loop"), "Video")
        for key in ("frame_rate", "context_length", "duration"):
            if key in video:
                _number(video[key], FIELDS[key])
        if "vhs" in video:
            vhs = video["vhs"]
            _object(vhs, ("frame_load_cap", "skip_first_frames", "select_every_nth", "skip_count", "skip_policy"), name="Frame loading")
            for key in ("frame_load_cap", "skip_first_frames", "select_every_nth"):
                _number(vhs[key], FIELDS[key])
            _counter(vhs["skip_count"], "Context skip count")
            _choice(vhs["skip_policy"], ("fixed", "increment"), "Context skip queue policy")
        if "loop" in video:
            _object(video["loop"], ("loop_count", "overlap"), name="Loop")
            for key in ("loop_count", "overlap"):
                _number(video["loop"][key], FIELDS[key])
            if "context_length" not in video:
                raise ValueError("Loop requires Context to be enabled.")
    if "seed" in config:
        _object(config["seed"], ("value", "policy"), name="Seed")
        _counter(config["seed"]["value"], "Seed")
        _choice(config["seed"]["policy"], ("fixed", "random", "increment", "decrement"), "Seed policy")
    return config


def date_folder(config, now=None):
    date = config["folder"].get("date_time")
    return (now or datetime.now(timezone.utc).astimezone()).strftime(date["format"]) if date else ""


def folder_pipe(config, output_directory, now=None):
    folder = config["folder"]
    path = normalize_relative_folder_path(folder["root"])
    if "date_time" in folder:
        date = normalize_relative_folder_path(date_folder(config, now))
        path = os.path.join(date, path) if folder["date_time"]["position"] == "prefix" else os.path.join(path, date)
    if "batch" in folder:
        path = os.path.join(path, format_batch(folder["batch"]["name"], folder["batch"]["number"]))
    pipe = {"path": os.path.join(output_directory, path), "batch_size": int(config["batch_size"])}
    if "size" in config:
        size = config["size"]
        pipe.update(width=int(size["width"]), height=int(size["height"]))
    if config["mode"] == "video":
        video = config["video"]
        pipe["fps"] = float(video["frame_rate"])
        if "context_length" in video:
            pipe["context_length"] = int(video["context_length"])
        if "duration" in video:
            pipe["duration"] = float(video["duration"])
        if "loop" in video:
            pipe.update({key: int(value) for key, value in video["loop"].items()})
        if "vhs" in video:
            vhs = video["vhs"]
            pipe.update({key: int(vhs[key]) for key in ("frame_load_cap", "skip_first_frames", "select_every_nth")})
            if "context_length" in video:
                pipe["skip_first_frames"] += int(video["context_length"]) * int(vhs["skip_count"])
                if video.get("loop", {}).get("loop_count", 0) > 0:
                    pipe["frame_load_cap"] = int(video["context_length"]) * int(video["loop"]["loop_count"])
    if "seed" in config:
        seed = config["seed"]
        pipe["seed"] = secrets.randbits(64) if seed["policy"] == "random" else int(seed["value"])
    return pipe
