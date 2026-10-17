# Exact standalone seed configuration. History belongs to workflow editor state.

import json
import re
import secrets

WIDGET_TYPE = "ECLIPSE_NOVA_SEED"


def default_configuration():
    return {"version": 1, "bits": 64, "seed": {"value": "0", "policy": "fixed"}}


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > 1024:
        raise ValueError("Seed configuration must be a JSON string of at most 1024 characters.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid Seed configuration JSON.") from error
    if not isinstance(config, dict) or set(config) != {"version", "bits", "seed"}:
        raise ValueError("Seed configuration has missing or unsupported fields.")
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 Seed configuration.")
    if type(config["bits"]) is not int or config["bits"] not in (32, 64):
        raise ValueError("Seed bit depth must be 32 or 64.")
    seed = config["seed"]
    if not isinstance(seed, dict) or set(seed) != {"value", "policy"}:
        raise ValueError("Seed requires a decimal value and queue policy.")
    if seed["policy"] not in ("fixed", "random", "increment", "decrement"):
        raise ValueError("Unknown seed queue policy.")
    if (not isinstance(seed["value"], str)
            or not re.fullmatch(r"0|[1-9][0-9]{0,19}", seed["value"])
            or int(seed["value"]) >= 2 ** config["bits"]):
        raise ValueError(f"Seed must be an unsigned {config['bits']}-bit decimal value.")
    return config


def resolve_configuration(raw):
    config = validate_configuration(raw)
    seed = secrets.randbits(config["bits"]) if config["seed"]["policy"] == "random" else int(config["seed"]["value"])
    config["seed"] = {"value": str(seed), "policy": "fixed"}
    return seed, json.dumps(config)
