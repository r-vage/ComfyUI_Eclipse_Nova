# Structured caption controls; all rendering still uses the shared lyric engine.
import copy
import json
import re
import secrets

from .fonts import default_caption_font, get_font_list, get_font_path
from .lyric_alignment import LANGUAGES
from .lyric_animation import ANIMATED_MODES, ROTATION_AXES
from .lyric_qwen import CHOICES as WORD_TIMING_CHOICES
from .lyric_qwen import TIP as WORD_TIMING_TIP
from .resolution_sizing import number, require_choice, require_fields, require_number

WIDGET_TYPE = "ECLIPSE_NOVA_LYRIC_CAPTIONS"
NUMBERS = {
    "width": number("Width", 720, 16, 4096, 2),
    "height": number("Height", 1280, 16, 4096, 2),
    "fps": number("FPS", 24, 1, 120, 0.1),
    "font_size": number("Font size", 80, 8, 512),
    "margin_x": number("Margin X", 40, 0, 2048),
    "margin_y": number("Margin Y", 40, 0, 2048),
    "outline_width": number("Outline width", 3, 0, 32),
    "caption_transparency": number("Transparency (%)", 0, 0, 100, 0.1),
    "glow_intensity": number("Intensity", 5, 2, 20),
    "glow_range": number("Range", 25, 1, 500),
    "glow_blur": number("Blur", 15, 0, 500),
    "timing_adjustment": number("Timing adjustment (s)", 0, -86400, 86400, 0.1),
    "circle_radius": number("Circle radius (%)", 30, 0, 50, 0.5),
    "float_distance": number("Float distance (%)", 1.5, 0, 20, 0.1),
    "fade_in": number("Fade in (s)", 0.5, 0, 2, 0.1),
    "fade_out": number("Fade out (s)", 0.5, 0, 2, 0.1),
    "min_display": number("Minimum hold (s)", 0.7, 0, 3, 0.1),
    "max_words": number("Words per phrase", 4, 1, 12),
    "max_simultaneous": number("Simultaneous items", 5, 1, 8),
}
COLORS = {
    "text_color": ("Text", "#ffffff"),
    "highlight_color": ("Active word", "#ffff00"),
    "outline_color": ("Outline", "#616161"),
    "background_color": ("Background", "#000000"),
    "glow_inner_color": ("Inner glow", "#2ec0ff"),
    "glow_outer_color": ("Outer glow", "#006eff"),
}
CHOICES = {
    "mode": {"whole-line": "Whole line", "active-word": "Active word",
             "floating-words": "Float words", "floating-lines": "Float lines",
             "rotating-words": "Rotate words", "rotating-lines": "Rotate lines"},
    "language": {key: key for key in ("Auto", *LANGUAGES)},
    "device": {"auto": "Auto", "cpu": "CPU", "cuda": "CUDA"},
    "position": {f"{v}_{h}": f"{v.title()} {h}" for v in ("top", "center", "bottom") for h in ("left", "center", "right")},
    "rotation_axis": {key: key for key in ROTATION_AXES},
    "unmatched_passages": {"omit": "Omit", "transcribe": "Transcribe"},
    "word_timing": WORD_TIMING_CHOICES,
}
TIPS = {
    "word_timing": WORD_TIMING_TIP,
    "font_size": "Maximum font size. Long captions shrink to fit the canvas, margins and effects.",
    "caption_transparency": "Fade text, outline, highlight and glow together. 100% hides captions; background and audio are unchanged.",
    "glow_intensity": "Glow buildup iterations; more creates denser glow.",
    "glow_range": "Maximum glow expansion distance in pixels.",
    "glow_blur": "Blur radius applied to each glow step.",
    "timing_adjustment": "Positive values delay captions. trim_start and duration trim the full soundtrack and captions together.",
    "circle_radius": "Caption centers stay inside a circle centered on the video, as a percentage of its shorter dimension.",
    "float_distance": "Maximum movement as a percentage of the shorter canvas dimension.",
    "fade_in": "Fade-in before the minimum readable hold, shortened when slots or the next rotating caption need room.",
    "fade_out": "Fade-out after the sung span and minimum hold. Floating items may overlap; rotating items finish by the next onset.",
    "min_display": "Minimum full-opacity hold, excluding fades. Also groups fast words. Shortened when necessary; sung onsets never move.",
    "max_words": "Maximum words per phrase. Indivisible timed spans and attached untimed text stay intact.",
    "max_simultaneous": "Maximum visible floating items, including outgoing fades.",
    "rotation_axis": "Turning sign rotates vertically; Flipping card rotates horizontally. Speed follows lyric timing.",
    "unmatched_passages": "Transcribe fills gaps with recognized words when supplied lyrics cannot be aligned. Review additions in timing_json.",
}


def default_configuration():
    return {
        "version": 1,
        "parameters": {
            **{key: spec["default"] for key, spec in NUMBERS.items()},
            **{key: spec[1] for key, spec in COLORS.items()},
            "font_file": default_caption_font(), "mode": "floating-words", "language": "en",
            "device": "auto", "position": "bottom_center", "rotation_axis": "Turning sign",
            "unmatched_passages": "omit", "enable_glow": False, "word_timing": "whisper",
        },
        "seed": {"source": "local", "value": "42", "policy": "fixed"},
    }


def editor_spec():
    return copy.deepcopy({"numbers": NUMBERS, "colors": COLORS, "choices": CHOICES,
                          "tips": TIPS, "fonts": get_font_list(), "animated": ANIMATED_MODES})


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("Caption configuration must be JSON text of at most 16 KiB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid caption configuration JSON.") from error
    require_fields(config, ("version", "parameters", "seed"))
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 caption configuration.")
    params = config["parameters"]
    if isinstance(params, dict):
        params.setdefault("word_timing", "whisper")
    require_fields(params, (*NUMBERS, *COLORS, *CHOICES, "font_file", "enable_glow"), name="Caption settings")
    for key, spec in NUMBERS.items():
        require_number(params[key], spec)
    for key, choices in CHOICES.items():
        require_choice(params[key], choices, key.replace("_", " ").title())
    for key in COLORS:
        if not isinstance(params[key], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", params[key]):
            raise ValueError(f"{COLORS[key][0]} must be a six-digit hex color.")
    if type(params["enable_glow"]) is not bool:
        raise ValueError("Glow must be enabled or disabled.")
    font = params["font_file"]
    if not isinstance(font, str) or not font or len(font) > 255 or "\\" in font or "\0" in font:
        raise ValueError("Select a font filename from models/fonts.")
    get_font_path(font)
    seed = config["seed"]
    require_fields(seed, ("source", "value", "policy"), name="Seed")
    if seed["source"] != "local" or seed["policy"] not in ("fixed", "random", "increment", "decrement"):
        raise ValueError("Expected a local seed with a valid queue policy.")
    if (not isinstance(seed["value"], str) or not re.fullmatch(r"0|[1-9][0-9]{0,19}", seed["value"])
            or int(seed["value"]) > 2**64 - 1):
        raise ValueError("Seed must be an unsigned 64-bit decimal value.")
    # Local dimensions remain valid even when currently overridden.
    resolve_parameters(config)
    return config


def resolve_parameters(config, width=None, height=None, fps=None):
    params = dict(config["parameters"])
    for key, value in (("width", width), ("height", height), ("fps", fps)):
        if value is not None:
            params[key] = require_number(value, NUMBERS[key])
    for key in ("width", "height"):
        if params[key] % 2:
            raise ValueError(f"{key.title()} must be an even number of pixels.")
    for key, spec in NUMBERS.items():
        if spec["step"] in (1, 2):
            params[key] = int(params[key])
    return params


def resolve_seed(config):
    return secrets.randbits(64) if config["seed"]["policy"] == "random" else int(config["seed"]["value"])
