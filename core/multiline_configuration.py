# Literal multiline text, optional prompt filtering and normalized list output.

import json

from .prompt_filter import filter_prompt

WIDGET_TYPE = "ECLIPSE_NOVA_MULTILINE"
MAX_TEXT_LENGTH = 1024 * 1024
MAX_CONFIG_LENGTH = 8 * MAX_TEXT_LENGTH
DEFAULT_CONFIGURATION = json.dumps({"version": 1, "text": "", "filter": False, "preview": False, "stop": False})


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > MAX_CONFIG_LENGTH:
        raise ValueError(f"Multiline configuration must be a JSON string of at most {MAX_CONFIG_LENGTH} characters.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid multiline configuration JSON.") from error
    if not isinstance(config, dict) or not {"version", "text"} <= set(config) <= {"version", "text", "filter", "preview", "stop"}:
        raise ValueError("Multiline configuration requires version and text, with optional filter, preview and stop.")
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 multiline configuration.")
    if not isinstance(config["text"], str) or len(config["text"]) > MAX_TEXT_LENGTH:
        raise ValueError(f"Text must be a string of at most {MAX_TEXT_LENGTH} characters.")
    for key in ("filter", "preview", "stop"):
        if key in config and not isinstance(config[key], bool):
            raise ValueError(f"{key.capitalize()} must be a boolean.")
    return config


def text_outputs(config, input_string=None):
    # The caller supplies a validated configuration so execution parses it once.
    text = config["text"]
    if config.get("filter", False):
        filtered = filter_prompt(input_string, text)
        return filtered, [line.strip() for line in filtered.split("\n") if line.strip()] or [""]
    prefix = input_string if isinstance(input_string, str) else ""
    # The full string keeps both inputs verbatim, including their line endings.
    full_string = " ".join(part for part in (prefix, text) if part)
    prefix = prefix.strip()
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if prefix and lines:
        lines = [f"{prefix} {line}" for line in lines]
    # An empty Python list would prevent downstream ComfyUI list mapping.
    return full_string, lines or [prefix]
