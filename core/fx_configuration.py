# Active FX settings are serialized; disabled effect drafts belong to the editor.
import copy
import json
import re

from .fonts import default_font, get_font_list, get_font_path
from .image_fx import POSITIONS, render_image_with_fx, render_text_with_fx
from .resolution_sizing import number, require_choice, require_fields, require_number

WIDGET_TYPE = "ECLIPSE_NOVA_FX_CONFIGURATION"
NUMBERS = {
    "image_scale": number("Scale (%)", 25, 1, 500),
    "opacity": number("Opacity (%)", 100, 0, 100),
    "margin_x": number("Margin X", 20, 0, 4000),
    "margin_y": number("Margin Y", 10, 0, 4000),
    "font_size": number("Font size", 48, 1, 2500),
    "text_scale": number("Scale (%)", 100, 1, 500),
    "char_per_line": number("Wrap at characters", 80, 1, 8096),
    "leading": number("Line spacing", 4, 0, 500),
    "stroke_width": number("Stroke width", 2, 1, 100),
    "glow_intensity": number("Intensity", 5, 2, 20),
    "glow_range": number("Range", 25, 1, 500),
    "glow_blur": number("Blur", 15, 0, 500),
    "shadow_offset_x": number("Offset X", 5, -500, 500),
    "shadow_offset_y": number("Offset Y", 5, -500, 500),
    "shadow_grow": number("Grow", 6, 0, 200),
    "shadow_blur": number("Blur", 18, 0, 200),
    "shadow_opacity": number("Opacity (%)", 50, 0, 100),
}
COLORS = {
    "text_color": ("Text color", "#ffffff"),
    "stroke_color": ("Stroke color", "#000000"),
    "glow_inner_color": ("Inner color", "#2ec0ff"),
    "glow_outer_color": ("Outer color", "#006eff"),
    "shadow_color": ("Shadow color", "#000000"),
}
CHOICES = {
    "position": {key: key.replace("_", " ").title() for key in POSITIONS},
    "text_align": {key: key.title() for key in ("left", "center", "right")},
}
GROUPS = {
    "image": ("image_scale", "opacity", "position", "margin_x", "margin_y", "invert_mask"),
    "text": ("text", "font_file", "font_size", "text_scale", "text_color", "text_align",
             "char_per_line", "leading", "opacity", "position", "margin_x", "margin_y"),
    "glow": ("glow_intensity", "glow_range", "glow_blur", "glow_inner_color", "glow_outer_color"),
    "shadow": ("shadow_offset_x", "shadow_offset_y", "shadow_grow", "shadow_blur", "shadow_color", "shadow_opacity"),
    "stroke": ("stroke_width", "stroke_color"),
}
MAX_TEXT = 16384


def group_defaults(group):
    values = {**{key: value["default"] for key, value in NUMBERS.items()},
              **{key: value[1] for key, value in COLORS.items()},
              "position": "bottom_right", "invert_mask": True, "text": "© Eclipse Nova",
              "text_align": "left"}
    if group == "text":
        values["font_file"] = default_font()
    return {key: values[key] for key in GROUPS[group]}


def effects(kind):
    return ("stroke", "glow", "shadow") if kind == "text" else ("glow", "shadow")


def default_configuration(kind):
    require_choice(kind, ("image", "text"), "FX node")
    return {"version": 1, "kind": kind, "parameters": group_defaults(kind),
            **{key: None for key in effects(kind)}}


def editor_spec(kind):
    return copy.deepcopy({
        "kind": kind, "numbers": NUMBERS, "colors": COLORS, "choices": CHOICES,
        "groups": GROUPS, "maxText": MAX_TEXT,
        "defaults": {key: group_defaults(key) for key in effects(kind)},
        "fonts": get_font_list() if kind == "text" else [],
    })


def validate_group(value, group):
    require_fields(value, GROUPS[group], name=f"{group.title()} settings")
    for key, setting in value.items():
        if key in NUMBERS:
            require_number(setting, NUMBERS[key])
        elif key in CHOICES:
            require_choice(setting, CHOICES[key], key.replace("_", " ").title())
        elif key in COLORS:
            if not isinstance(setting, str) or not re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", setting):
                raise ValueError(f"{COLORS[key][0]} must be a hex color, such as #00ffcc.")
        elif key == "invert_mask" and type(setting) is not bool:
            raise ValueError("Invert mask must be enabled or disabled.")
        elif key == "text" and (not isinstance(setting, str) or len(setting) > MAX_TEXT):
            raise ValueError(f"Text must be a string of at most {MAX_TEXT} characters.")
        elif key == "font_file":
            if not isinstance(setting, str) or not setting or len(setting) > 255 or "\\" in setting:
                raise ValueError("Select a font filename from models/fonts.")
            get_font_path(setting)


def validate_configuration(raw, kind):
    if not isinstance(raw, str) or len(raw) > 131072:
        raise ValueError("FX configuration must be a JSON string of at most 128 KB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid FX configuration JSON.") from error
    require_fields(config, ("version", "kind", "parameters", *effects(kind)), name="FX configuration")
    if type(config["version"]) is not int or config["version"] != 1 or config["kind"] != kind:
        raise ValueError(f"Expected version 1 {kind} FX configuration.")
    validate_group(config["parameters"], kind)
    for key in effects(kind):
        if config[key] is not None:
            validate_group(config[key], key)
    return config


def render_configuration(raw, kind, **inputs):
    config = validate_configuration(raw, kind)
    parameters = dict(config["parameters"])
    for key in effects(kind):
        parameters.update(config[key] if config[key] is not None else group_defaults(key))
        if key == "stroke":
            if config[key] is None:
                parameters["stroke_width"] = 0
        else:
            parameters[f"enable_{key}"] = config[key] is not None
    if kind == "text":
        text_input = inputs.pop("text_input", None)
        if text_input is not None:
            if not isinstance(text_input, str) or len(text_input) > MAX_TEXT:
                raise ValueError(f"Connected text must be a string of at most {MAX_TEXT} characters.")
            parameters["text"] = text_input
    for key in NUMBERS:
        if key in parameters:
            parameters[key] = int(parameters[key])
    if kind == "image":
        return render_image_with_fx(**parameters, **inputs)
    return render_text_with_fx(**parameters, **inputs)
