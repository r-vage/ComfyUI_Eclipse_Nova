# Structured Prompt Forge configuration and exact local/input seed handling.

import json
import re
import secrets

from . import prompt_forge

WIDGET_TYPE = "ECLIPSE_NOVA_PROMPT_FORGE"
MAX_SEED = 2**64 - 1
MAX_TEXT_LENGTH = 65536
MAX_CONFIG_BYTES = 2 * 1024 * 1024
TEXT_FIELDS = {
    "prefix": ("Prefix", "Add comma- or newline-separated tags before all other tags."),
    "taglists_must_include": ("Required tags", "Select only taglists containing every listed tag. These tags also appear in the output."),
    "custom_prompt": ("Custom prompt", "Add tags after the required tags and before the generated tags."),
    "exclude_tag_categories": ("Category exclusions", "Remove generated tags in these categories. Explicit prefix, required and custom tags remain."),
}
FEATURES = {
    "general": ("General", "Include the general content-rating pool."),
    "questionable": ("Questionable", "Include the questionable content-rating pool."),
    "sensitive": ("Sensitive", "Include the sensitive content-rating pool."),
    "explicit": ("Explicit", "Include the explicit content-rating pool."),
    "replace_underscores": ("Underscores", "Replace underscores with spaces in the final prompt when enabled."),
    "ignore_missing": ("Ignore missing", "Ignore required tags absent from every selected pool when choosing a taglist. They remain in the output."),
    "categories": ("Categories", "Filter generated tags using the categorized corpus and Category exclusions."),
}


def default_configuration():
    return {
        "version": 1,
        "features": list(prompt_forge.DEFAULT_FEATURES),
        "texts": {
            "prefix": "",
            "taglists_must_include": prompt_forge.DEFAULT_TAGLISTS_MUST_INCLUDE,
            "custom_prompt": "",
            "exclude_tag_categories": prompt_forge.DEFAULT_EXCLUDE_CATEGORIES,
        },
        "seed": {"source": "local", "value": "0", "policy": "fixed"},
    }


def editor_spec():
    return {
        "features": [{"key": key, "label": label, "tooltip": tip} for key, (label, tip) in FEATURES.items()],
        "texts": [{"key": key, "label": label, "tooltip": tip} for key, (label, tip) in TEXT_FIELDS.items()],
        "ratings": [rating for rating, _ in prompt_forge.CONTENT_POOL_FILES],
        "maxText": MAX_TEXT_LENGTH,
    }


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ValueError("Prompt Forge configuration must be a JSON string of at most 2 MiB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid Prompt Forge configuration JSON.") from error
    if not isinstance(config, dict) or set(config) != {"version", "features", "texts", "seed"}:
        raise ValueError("Prompt Forge configuration has missing or unsupported fields.")
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 Prompt Forge configuration.")
    features = config["features"]
    if not isinstance(features, list) or any(not isinstance(key, str) or key not in FEATURES for key in features):
        raise ValueError("Unknown Prompt Forge mode option.")
    if len(set(features)) != len(features):
        raise ValueError("Prompt Forge mode options must be unique.")
    if not any(rating in features for rating, _ in prompt_forge.CONTENT_POOL_FILES):
        raise ValueError("Select at least one content-rating pool in Mode.")
    texts = config["texts"]
    if not isinstance(texts, dict) or texts.keys() != TEXT_FIELDS.keys():
        raise ValueError("Prompt Forge requires its four text sections.")
    for key, value in texts.items():
        if not isinstance(value, str) or "\0" in value or len(value) > MAX_TEXT_LENGTH:
            raise ValueError(f"{TEXT_FIELDS[key][0]} must contain at most {MAX_TEXT_LENGTH} characters and no NUL characters.")
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
    if config["seed"]["source"] == "local" and config["seed"]["policy"] == "random":
        return float("nan")
    names = [filename for rating, filename in prompt_forge.CONTENT_POOL_FILES if rating in config["features"]]
    if "categories" in config["features"]:
        names.extend(("categories.txt", "categorized_tags.txt"))
    files = []
    for name in names:
        path = prompt_forge.DATA_DIRECTORY / name
        try:
            stat = path.stat()
            files.append((name, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        except OSError:
            files.append((name, None))
    return tuple(files)


def generate(raw, seed_input=None):
    config = validate_configuration(raw)
    if config["seed"]["source"] == "input":
        if type(seed_input) is not int or not 0 <= seed_input <= MAX_SEED:
            raise ValueError("Connect a valid unsigned 64-bit seed_input or enable Local seed.")
        seed = seed_input
    else:
        seed = secrets.randbits(64) if config["seed"]["policy"] == "random" else int(config["seed"]["value"])
    return prompt_forge.build_prompt(seed, config["features"], **config["texts"]), seed
