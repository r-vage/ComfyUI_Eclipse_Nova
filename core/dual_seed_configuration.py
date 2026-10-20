# Two independent seed policies sharing one bit depth.
import json

from .seed_configuration import resolve_configuration as resolve_seed
from .seed_configuration import validate_configuration as validate_seed

WIDGET_TYPE = "ECLIPSE_NOVA_DUAL_SEED"


def default_configuration():
    return {"version": 1, "bits": 64, "seeds": {
        key: {"value": "0", "policy": "fixed"} for key in ("image", "prompt")}}


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > 2048:
        raise ValueError("Dual Seed configuration must be JSON text of at most 2048 characters.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid Dual Seed configuration JSON.") from error
    if (not isinstance(config, dict) or set(config) != {"version", "bits", "seeds"}
            or not isinstance(config["seeds"], dict) or set(config["seeds"]) != {"image", "prompt"}):
        raise ValueError("Dual Seed requires Image and Prompt seeds with a shared bit depth.")
    for seed in config["seeds"].values():
        validate_seed(json.dumps({"version": config["version"], "bits": config["bits"], "seed": seed}))
    return config


def resolve_configuration(raw):
    config = validate_configuration(raw)
    values = []
    for key in ("image", "prompt"):
        value, _ = resolve_seed(json.dumps({"version": 1, "bits": config["bits"], "seed": config["seeds"][key]}))
        values.append(value)
        config["seeds"][key] = {"value": str(value), "policy": "fixed"}
    return values, json.dumps(config)
