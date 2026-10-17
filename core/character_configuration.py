# Structured panel contracts for character reference and sheet tools.
import copy
import json

from .character_references import MODES, ROLES
from .character_sheets import (
    GENERATION_MODES,
    MANNEQUIN_ATTRIBUTES,
    STAGES,
    mannequin_options,
)
from .resolution_sizing import number, require_choice, require_fields, require_number

WIDGET_TYPE = "ECLIPSE_NOVA_CHARACTER"
MAX_TEXT = 65536
TITLES = {
    "prepare": "Character Reference Prepare", "reference_pack": "Character Reference Pack",
    "sheet_pack": "Character Sheet Pack", "sheet_split": "Character Sheet Split",
}
TEXTS = {
    "prepare": {"description": ("Description", ""), "instructions": ("Instructions", "")},
    "reference_pack": {
        "identity": ("Identity", "The same adult character throughout the dataset."),
        "body_description": ("Body proportions", ""),
        "outfit": ("Outfit", "Plain grey cardigan, blue jeans and white sneakers."),
        "scene": ("Scene", "Plain white studio background and light floor, soft natural light."),
        "extra_rules": ("Extra rules", ""),
    },
    "sheet_pack": {"details": ("Details", "")}, "sheet_split": {},
}
NUMBERS = {
    "prepare": {},
    "reference_pack": {"width": number("Width", 832, 256, 2048, 32), "height": number("Height", 1216, 256, 2048, 32)},
    "sheet_pack": {"width": number("Width", 1536, 256, 2048, 32), "height": number("Height", 864, 256, 2048, 32)},
    "sheet_split": {
        "front_end": number("Front / rear boundary", 0.333, 0.01, 0.98, 0.001),
        "rear_end": number("Rear / portrait boundary", 0.666, 0.02, 0.99, 0.001),
        "gutter": number("Gutter", 0.004, 0, 0.09, 0.001),
    },
}
CHOICES = {
    "prepare": {"role": {value: value.title() for value in ROLES}, "mode": {value: value.title() for value in MODES}},
    "reference_pack": {},
    "sheet_pack": {"stage": {value: value.title() for value in STAGES}, "generation_mode": {value: value for value in GENERATION_MODES}},
    "sheet_split": {"mode": {"auto": "Auto", "manual": "Manual"}},
}
TOGGLES = {"use_front_body": "Front body", "use_rear_body": "Rear body", "use_wardrobe": "Wardrobe", "use_rear": "Rear"}
TIPS = {
    "description": "Appends to the preparation positive from the file. A connected positive_override replaces this too.",
    "instructions": "Additional preparation instructions, after Description. Does not change the negative or assembly rules.",
    "identity": "Identity, hair and distinctive features preserved in both assembly and dataset prompts.",
    "body_description": "Visible build and relative proportions. Supplements the body image or guides physique without one.",
    "outfit": "Fixed wardrobe and choices for missing items. Clear the example outfit when using a different reference.",
    "scene": "Background and lighting for the review image only; excluded from character_lock. Set the planner scene separately.",
    "extra_rules": "Appends to both character_lock and anchor_prompt. Avoid fixed poses if the planner should vary them.",
    "details": "Mannequin: physique; wardrobe: missing outfit choices; sheet: identity and complete outfit; dataset: continuity without fixed pose instructions. Appends even with a positive override.",
    "width": "Canvas width, a multiple of 32 from 256 to 2048. A connected non-None width overrides the local value. Set the Qwen encoder resolution to 0.",
    "height": "Canvas height, a multiple of 32 from 256 to 2048. A connected non-None height overrides the local value. Supporting mannequin/sheet references keep their own aspect ratios.",
    "front_end": "Manual front/rear boundary as a fraction of the full sheet width. Ignored in Auto mode.",
    "rear_end": "Manual rear/portrait boundary as a fraction of the full sheet width. Must follow the front/rear boundary.",
    "gutter": "Fraction of full sheet width trimmed from both sides of every crop, in either mode. Zero retains all pixels.",
    "use_front_body": "Mannequin Reference mode: use the frontal physique image. Disabled skips its branch.",
    "use_rear_body": "Mannequin Reference mode: use the rear physique image. Disabled skips its branch.",
    "use_wardrobe": "Sheet: use the wardrobe board. Disabled skips its branch; describe the complete outfit in Details.",
    "use_rear": "Dataset: include the approved rear crop. Disabled skips its branch; does not change shot direction.",
    "role": "Select the file prompt category. Changing role does not change connected prompt overrides.",
    "mode": "Reference passes the source; Extract generates from it; Generate uses text; Disabled omits the reference. Select requests only the needed branch.",
    "stage": "Mannequin builds the guide; Wardrobe prepares outfit views; Sheet dresses the guide; Dataset uses approved single panels. Keep connected prompt overrides appropriate to the stage.",
    "generation_mode": "Preset skips all image inputs. Reference uses optional layout and physique images. Gender applies in both; other attributes apply only to Preset.",
}


def default_configuration(kind):
    require_choice(kind, TITLES, "Character tool")
    parameters = {key: spec["default"] for key, spec in NUMBERS[kind].items()}
    parameters.update({key: default for key, (_, default) in TEXTS[kind].items()})
    if kind == "prepare":
        parameters.update(role="face", mode="reference")
    elif kind == "sheet_pack":
        parameters.update(stage="sheet", generation_mode="Preset", **dict.fromkeys(TOGGLES, True))
        parameters.update({key: "average" if key == "build" else "unspecified" for key in MANNEQUIN_ATTRIBUTES})
    elif kind == "sheet_split":
        parameters["mode"] = "manual"
    return {"version": 1, "kind": kind, "parameters": parameters}


def editor_spec(kind):
    choices = copy.deepcopy(CHOICES[kind])
    if kind == "sheet_pack":
        choices.update({key: {value: value for value in values} for key, values in mannequin_options().items()})
    return copy.deepcopy({"kind": kind, "title": TITLES[kind], "numbers": NUMBERS[kind], "texts": TEXTS[kind],
                          "choices": choices, "toggles": TOGGLES if kind == "sheet_pack" else {}, "tips": TIPS,
                          "keys": list(default_configuration(kind)["parameters"]), "maxText": MAX_TEXT})


def _text(value, name):
    if not isinstance(value, str) or len(value) > MAX_TEXT or "\0" in value:
        raise ValueError(f"{name} must be text of at most {MAX_TEXT} characters without NUL characters.")
    return value


def _dimension(value, spec):
    require_number(value, spec)
    if value % 32:
        raise ValueError(f"{spec['label']} must be a multiple of 32.")
    return int(value)


def validate_configuration(raw, kind):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 4 * 1024 * 1024:
        raise ValueError("Character configuration must be JSON text smaller than 4 MiB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid character configuration JSON.") from error
    require_fields(config, ("version", "kind", "parameters"))
    if type(config["version"]) is not int or config["version"] != 1 or config["kind"] != kind:
        raise ValueError(f"Expected version 1 {TITLES[kind]} configuration.")
    p = config["parameters"]
    require_fields(p, default_configuration(kind)["parameters"], name=TITLES[kind])
    for key, spec in NUMBERS[kind].items():
        if key in ("width", "height"):
            p[key] = _dimension(p[key], spec)
        else:
            require_number(p[key], spec)
    for key in TEXTS[kind]:
        _text(p[key], key)
    for key, choices in CHOICES[kind].items():
        require_choice(p[key], choices, key)
    if kind == "sheet_pack":
        for key in TOGGLES:
            if type(p[key]) is not bool:
                raise ValueError(f"{key} must be enabled or disabled.")
        for key in MANNEQUIN_ATTRIBUTES:
            _text(p[key], key)
        # The engine validates active selections against the current editable
        # file. Inactive saved selections need not exist in a different stage.
    if kind == "sheet_split" and p["mode"] == "manual" and p["front_end"] >= p["rear_end"]:
        raise ValueError("The rear / portrait boundary must follow the front / rear boundary.")
    return config


def resolved_parameters(config, **overrides):
    kind = config["kind"]
    parameters = config["parameters"].copy()
    for key, value in overrides.items():
        if value is None:
            continue
        if key in TEXTS[kind]:
            parameters[key] = _text(value, key)
        elif key in ("width", "height") and key in NUMBERS[kind]:
            parameters[key] = _dimension(value, NUMBERS[kind][key])
        else:
            raise ValueError(f"Unsupported character input override: {key}.")
    return parameters
