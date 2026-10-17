# Structured configuration for the renderer-independent Prompt Styler.

import json
import random

from .prompt_styler import apply_prompt_style
from .styles import find_template_by_name, get_all_styles

WIDGET_TYPE = "ECLIPSE_NOVA_PROMPT_STYLER"
MODES = ("tag_based", "natural_language", "custom")
POLICIES = ("fixed", "random", "increment", "decrement")
FLAGS = ("apply_to_positive", "apply_to_negative", "spaces_to_underscores", "log_prompt")


def default_configuration():
    return {
        "version": 1,
        "style_mode": "tag_based",
        "style": "base",
        "index": 0,
        "policy": "fixed",
        "apply_to_positive": True,
        "apply_to_negative": True,
        # Keep the serialized fields stable for saved workflows. The flag now
        # removes underscores; its former word limit no longer affects output.
        "spaces_to_underscores": False,
        "max_words_to_combine": 3,
        "log_prompt": False,
    }


def editor_spec():
    _, names = get_all_styles()
    return {"styles": {mode: list(names.get(mode, [])) for mode in MODES}}


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > 32768:
        raise ValueError("Prompt Styler configuration must be a JSON string of at most 32 KB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid Prompt Styler configuration JSON.") from error
    if not isinstance(config, dict) or config.keys() != default_configuration().keys():
        raise ValueError("Invalid Prompt Styler configuration fields.")
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 Prompt Styler configuration.")
    if config["style_mode"] not in MODES or config["policy"] not in POLICIES:
        raise ValueError("Unknown style library or index policy.")
    if not isinstance(config["style"], str) or not config["style"].strip() or len(config["style"]) > 2048:
        raise ValueError("Select a named style.")
    if type(config["index"]) is not int or not 0 <= config["index"] <= 999999:
        raise ValueError("Style index must be an integer between 0 and 999999.")
    if any(type(config[key]) is not bool for key in FLAGS):
        raise ValueError("Include options must be true or false.")
    if type(config["max_words_to_combine"]) is not int or not 2 <= config["max_words_to_combine"] <= 10:
        raise ValueError("Maximum words must be an integer between 2 and 10.")
    return config


def selected_template(config, *, randomize=True):
    styles, _ = get_all_styles()
    templates = styles.get(config["style_mode"], [])
    if not (config["apply_to_positive"] or config["apply_to_negative"]):
        return None
    if config["policy"] == "random":
        if not templates:
            raise ValueError("No styles available in this library. Refresh the style list.")
        return random.choice(templates) if randomize else templates[0]
    template = find_template_by_name(templates, config["style"])
    if template is None:
        raise ValueError(f"Style '{config['style']}' is unavailable in {config['style_mode']}. Refresh and select a style.")
    return template


def fingerprint(raw):
    config = validate_configuration(raw)
    if config["policy"] == "random" and (config["apply_to_positive"] or config["apply_to_negative"]):
        return float("nan")
    template = selected_template(config)
    return json.dumps(template, sort_keys=True)


def style_prompts(raw, text_positive, text_negative=""):
    config = validate_configuration(raw)
    template = selected_template(config)
    return apply_prompt_style(
        style_mode=config["style_mode"],
        style=template["name"] if template else config["style"],
        # A saved name remains authoritative if files are reordered on disk.
        index=-1,
        remove_underscores=config["spaces_to_underscores"],
        text_positive=text_positive,
        apply_to_positive=config["apply_to_positive"],
        apply_to_negative=config["apply_to_negative"],
        log_prompt=config["log_prompt"],
        text_negative=text_negative,
    )
