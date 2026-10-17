# Structured wildcard list configuration shared by execution and live preview.

import json
import re
import secrets

from . import wildcard_engine
from .wildcard_processing import expand_prompt, prompt_lines

WIDGET_TYPE = "ECLIPSE_NOVA_WILDCARD_LIST"
MAX_SEED = 2**64 - 1
MAX_TEXT_LENGTH = 65536
MAX_CONFIG_BYTES = 2 * 1024 * 1024


def default_configuration():
    return {
        "version": 1,
        "mode": "populate",
        "texts": {"prompt": "", "result": ""},
        "seed": {"source": "local", "value": "0", "policy": "fixed"},
    }


def editor_spec():
    return {"maxText": MAX_TEXT_LENGTH}


def _validate_text(text, label):
    if not isinstance(text, str) or "\0" in text or len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"{label} must contain at most {MAX_TEXT_LENGTH} characters and no NUL characters.")
    return text


def _substitution_text(value):
    if isinstance(value, list):
        # List items are one shared set of assignments, separated like lines
        # from a multiline string. Bound the combined size before joining.
        length = max(0, len(value) - 1)
        for item in value:
            length += len(_validate_text(item, "Substitutions"))
            if length > MAX_TEXT_LENGTH:
                raise ValueError(f"Combined substitutions must contain at most {MAX_TEXT_LENGTH} characters.")
        value = "\n".join(value)
    return _validate_text(value, "Substitutions")


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ValueError("Wildcard configuration must be a JSON string of at most 2 MiB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid wildcard configuration JSON.") from error
    if not isinstance(config, dict) or set(config) != {"version", "mode", "texts", "seed"}:
        raise ValueError("Wildcard configuration has missing or unsupported fields.")
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 wildcard configuration.")
    if config["mode"] not in ("populate", "fixed"):
        raise ValueError("Choose Populate or Fixed mode.")
    texts = config["texts"]
    if not isinstance(texts, dict) or set(texts) != {"prompt", "result"}:
        raise ValueError("Wildcard configuration requires Prompt and Result text.")
    for key, value in texts.items():
        _validate_text(value, key.title())
    seed = config["seed"]
    if not isinstance(seed, dict) or set(seed) != {"source", "value", "policy"}:
        raise ValueError("Seed requires a source, decimal value and queue policy.")
    if seed["source"] not in ("local", "input") or seed["policy"] not in ("fixed", "random", "increment", "decrement"):
        raise ValueError("Unknown seed source or queue policy.")
    if not isinstance(seed["value"], str) or not re.fullmatch(r"0|[1-9][0-9]{0,19}", seed["value"]) or int(seed["value"]) > MAX_SEED:
        raise ValueError("Seed must be an unsigned 64-bit decimal value.")
    return config


def fingerprint(raw):
    config = validate_configuration(raw)
    if config["mode"] == "fixed":
        return None
    if config["seed"]["source"] == "local" and config["seed"]["policy"] == "random":
        return float("nan")
    return wildcard_engine.get_wildcard_revision()


def generate(raw, wildcard_text=None, substitutions=None, seed_input=None, *, preview=False):
    config = validate_configuration(raw)
    if config["mode"] == "fixed":
        text = config["texts"]["result"]
        return text, prompt_lines(text), None
    if config["seed"]["source"] == "input":
        if type(seed_input) is not int or not 0 <= seed_input <= MAX_SEED:
            raise ValueError("Connect a valid unsigned 64-bit seed_input or enable Local seed.")
        seed = seed_input
    else:
        seed = secrets.randbits(64) if config["seed"]["policy"] == "random" and not preview else int(config["seed"]["value"])
    source = config["texts"]["prompt"] if wildcard_text is None else _validate_text(wildcard_text, "wildcard_text")
    if substitutions is not None:
        substitutions = _substitution_text(substitutions)
    text = expand_prompt(source, seed, substitutions)
    return text, prompt_lines(text), seed
