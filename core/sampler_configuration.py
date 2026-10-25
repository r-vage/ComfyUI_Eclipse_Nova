# Versioned configuration for the new Eclipse sampler panels.

import copy
import json
import math
import re
import secrets

from .common import get_samplers_comfy, get_schedulers_any
from .sampler_extras import extra_fields

WIDGET_TYPE = "ECLIPSE_NOVA_SAMPLER_CONFIGURATION"
MAX_SEED = 2**64 - 1


def editor_spec(profile):
    if profile == "advanced":
        return advanced_editor_spec()
    if profile == "detailer":
        return detailer_editor_spec()
    if profile not in ("settings", "sampler"):
        raise ValueError("Unknown sampler profile.")
    samplers = list(get_samplers_comfy())
    schedulers = list(get_schedulers_any())
    settings = profile == "settings"
    fields = {
        "sampler_name": {"label": "Sampler", "options": samplers, "default": "euler" if settings else "res_multistep"},
        "scheduler": {"label": "Scheduler", "options": schedulers, "default": "simple"},
        "steps": {"label": "Steps", "default": 30 if settings else 8, "min": 1, "max": 150 if settings else 10000, "step": 1, "integer": True},
        "cfg": {"label": "CFG", "default": 5.0 if settings else 1.0, "min": 1 if settings else 0, "max": 30 if settings else 100, "step": 0.1},
        "denoise": {"label": "Denoise", "default": 1.0, "min": 0, "max": 1, "step": 0.1},
        "allow_overwrite": {"label": "Allow IO inputs to override" if settings else "Use pipe settings", "default": False},
    }
    if settings:
        fields.update({
            "guidance": {"label": "Guidance", "default": 3.5, "min": 0, "max": 10, "step": 0.1},
            "sigmas_denoise": {"label": "Sigmas denoise", "default": 0.45, "min": 0, "max": 1, "step": 0.01},
            "noise_strength": {"label": "Noise strength", "default": 0.5, "min": 0, "max": 1, "step": 0.1},
            "upscale_value": {"label": "Upscale factor", "default": 1.5, "min": 0.1, "max": 10, "step": 0.1},
        })
    else:
        fields.update({
            "tiled_decode": {"label": "Tiled decode", "default": False},
            "alpha": {"label": "Alpha", "default": False},
            "tile_size": {"label": "Tile size", "default": 512, "min": 64, "max": 4096, "step": 32, "integer": True},
            "preview_mode": {"label": "Preview", "default": "Preview", "options": ["Preview", "None"]},
        })
    return {"profile": profile, "fields": fields, "seedDefault": "0" if settings else "42"}


def advanced_editor_spec():
    fields = editor_spec("sampler")["fields"]
    fields["steps"]["default"] = 16
    fields["sampler_name"]["default"] = "er_sde"
    fields["cfg"]["default"] = 3.0
    for key, label, default in [("two_stage", "Two-stage", True), ("latent_upscale", "Latent upscale", True),
                                ("add_noise", "Add noise", True), ("leftover_noise", "Keep leftover noise", True),
                                ("second_add_noise", "Add noise", True), ("second_leftover", "Keep leftover noise", False)]:
        fields[key] = {"label": label, "default": default}
    for key, label, default in [("start_step", "Start step", 0), ("end_step", "Stop step", 12),
                                ("second_start", "Start step", 9), ("second_end", "Stop step", 25)]:
        fields[key] = {"label": label, "default": default, "min": 0, "max": 10000, "step": 1, "integer": True}
    for key in ("steps", "cfg", "sampler_name", "scheduler"):
        fields["second_" + key] = copy.deepcopy(fields[key])
    fields["second_steps"]["default"] = 25
    fields["second_scheduler"]["default"] = "beta"
    fields["second_seed"] = {"label": "Stage 2 seed (optional)", "default": "", "seed": True}
    fields["seed_offset"] = {"label": "Stage 2 seed offset", "default": 88, "min": -2147483648, "max": 2147483647, "step": 1, "integer": True}
    fields["upscale_factor"] = {"label": "Scale factor", "default": 2.0, "min": 1, "max": 8, "step": 0.1}
    fields["upscale_method"] = {"label": "Method", "default": "bicubic", "options": ["nearest-exact", "bilinear", "area", "bicubic", "bislerp"]}
    fields.update(extra_fields())
    # Append to keep every existing IO KSampler socket index stable.
    fields["second_denoise"] = {"label": "Denoise", "default": 1.0, "min": 0, "max": 1, "step": 0.01,
                                "tooltip": "Stage 2 denoise strength when Start step is 0, like a standard KSampler. Ignored when Start step is above 0 so continuation uses the full schedule. 0 skips Stage 2 sampling; any latent upscale still applies."}
    return {"profile": "advanced", "fields": fields, "seedDefault": "42"}


def detailer_editor_spec():
    # The detailer's scheduler set includes Impact's additional schedules.
    from ..extern.impact.core import get_schedulers

    fields = {
        "allow_overwrite": {"label": "Use pipe settings", "default": False},
        "sampler_name": {"label": "Sampler", "options": list(get_samplers_comfy()), "default": "euler"},
        "scheduler": {"label": "Scheduler", "options": get_schedulers(), "default": "normal"},
        "steps": {"label": "Steps", "default": 20, "min": 1, "max": 10000, "step": 1, "integer": True},
        "cfg": {"label": "CFG", "default": 8.0, "min": 0, "max": 100, "step": 0.1},
        "denoise": {"label": "Denoise", "default": 0.5, "min": 0.0001, "max": 1, "step": 0.0001},
        "cycle": {"label": "Cycles", "default": 1, "min": 1, "max": 10, "step": 1, "integer": True},
        "guide_size": {"label": "Guide size", "default": 512.0, "min": 64, "max": 8192, "step": 8},
        "max_size": {"label": "Max size", "default": 1024.0, "min": 64, "max": 8192, "step": 8},
        "guide_size_for": {"label": "Guide size for", "default": True},
        "feather": {"label": "Blend feather", "default": 5, "min": 0, "max": 100, "step": 1, "integer": True},
        "noise_mask_feather": {"label": "Noise mask feather", "default": 20, "min": 0, "max": 100, "step": 1, "integer": True},
        "noise_mask": {"label": "Noise mask", "default": True},
        "force_inpaint": {"label": "Force inpaint", "default": True},
        "inpaint_model": {"label": "Inpaint model", "default": True},
        "tiled_encode": {"label": "Tiled encode", "default": True},
        "tiled_decode": {"label": "Tiled decode", "default": True},
        "live_preview": {"label": "Preview", "default": True},
    }
    return {"profile": "detailer", "fields": fields, "seedDefault": "0"}


def default_configuration(profile):
    fields = editor_spec(profile)["fields"]
    keys = ["sampler_name", "scheduler", "steps", "cfg", "denoise"] if profile == "settings" else fields
    config = {"version": 1, "profile": profile, "parameters": {key: copy.deepcopy(fields[key]["default"]) for key in keys}}
    if profile != "settings":
        config["seed"] = {"value": editor_spec(profile)["seedDefault"], "policy": "fixed"}
    return config


def validate_configuration(raw, profile):
    if not isinstance(raw, str) or len(raw) > 32768:
        raise ValueError("Sampler configuration must be a JSON string of at most 32 KB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid sampler configuration JSON.") from error
    if not isinstance(config, dict) or type(config.get("version")) is not int or config["version"] != 1 or config.get("profile") != profile:
        raise ValueError(f"Expected version 1 {profile} configuration.")
    if set(config) - {"version", "profile", "parameters", "seed"}:
        raise ValueError("Unknown sampler configuration field.")
    values = config.get("parameters")
    fields = editor_spec(profile)["fields"]
    if not isinstance(values, dict) or set(values) - fields.keys():
        raise ValueError("Unknown sampler parameter.")
    if profile == "advanced":
        values.setdefault("second_seed", "")
        values.setdefault("second_denoise", 1.0)
        for key, field in fields.items():
            if field.get("optional"):
                values.setdefault(key, field["default"])
    if profile == "sampler":
        values.setdefault("alpha", False)
    if profile == "detailer":
        values.setdefault("allow_overwrite", False)
    if profile != "settings" and set(values) != fields.keys():
        raise ValueError("Sampler configuration is missing required parameters.")
    if ("sigmas_denoise" in values) != ("noise_strength" in values):
        raise ValueError("Noise injection requires both sigmas denoise and noise strength.")
    for key, value in values.items():
        field = fields[key]
        if field.get("seed"):
            if not isinstance(value, str) or (value != "" and (not re.fullmatch(r"0|[1-9][0-9]{0,19}", value) or int(value) > MAX_SEED)):
                raise ValueError(f"{field['label']} must be empty or an unsigned 64-bit decimal value.")
        elif field.get("text"):
            if not isinstance(value, str) or len(value) > 4096 or not re.fullmatch(r"\s*(?:[0-9]{1,4}(?:\s*,\s*[0-9]{1,4})*)?\s*", value):
                raise ValueError(f"{field['label']} must be comma-separated layer indices (0–9999), or empty.")
        elif "options" in field:
            if not isinstance(value, str) or value not in field["options"]:
                raise ValueError(f"{field['label']}: {value!r} is unavailable on this server.")
        elif isinstance(field["default"], bool):
            if not isinstance(value, bool):
                raise ValueError(f"{field['label']} must be enabled or disabled.")
        elif type(value) not in (float, int) or not field["min"] <= value <= field["max"] or not math.isfinite(value) or (field.get("integer") and type(value) is not int):
            raise ValueError(f"{field['label']} must be {'an integer ' if field.get('integer') else ''}between {field['min']} and {field['max']}.")
    if profile == "advanced":
        if values['qwen_schedule'] and values['qwen_dynamic'] and values['qwen_max_tokens'] <= values['qwen_base_tokens']:
            raise ValueError('Qwen Max image tokens must exceed Base image tokens.')
        for prefix, enabled in [('dit', 'dit_guidance'), ('detail', 'detail_daemon')]:
            if values[enabled] and values[prefix + '_start'] >= values[prefix + '_end']:
                raise ValueError(f'{prefix}: Start must be below End.')
    if profile == "advanced" and values["two_stage"]:
        for start, end, steps in [("start_step", "end_step", "steps"), ("second_start", "second_end", "second_steps")]:
            if not 0 <= values[start] < min(values[end], values[steps]):
                raise ValueError("Each stage needs start < stop and start < total steps.")
    seed = config.get("seed")
    if "seed" in config:
        if not isinstance(seed, dict) or set(seed) != {"value", "policy"}:
            raise ValueError("Seed requires a decimal value and queue policy.")
        value = seed["value"]
        if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,19}", value) or int(value) > MAX_SEED:
            raise ValueError("Seed must be an unsigned 64-bit decimal value.")
        if seed["policy"] not in ("fixed", "random", "increment", "decrement"):
            raise ValueError("Unknown seed queue policy.")
    elif profile != "settings":
        raise ValueError("Sampler configuration requires a seed.")
    return config


def resolve_seed(seed):
    return secrets.randbits(64) if seed["policy"] == "random" else int(seed["value"])


def settings_pipe(config):
    values = config["parameters"]
    pipe = {key: round(value, 2) if isinstance(value, float) else value for key, value in values.items() if key != "allow_overwrite"}
    if "allow_overwrite" in values:
        pipe["_allow_overwrite"] = values["allow_overwrite"]
    if "seed" in config:
        pipe["seed"] = resolve_seed(config["seed"])
    return pipe
