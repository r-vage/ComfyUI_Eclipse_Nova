# Shot Planner panel contract and explicit text/seed input precedence.
import copy
import json
import re
import secrets

from .resolution_sizing import number, require_choice, require_fields, require_number
from .shot_planner import MAX_SHOTS
from .shot_planner_execution import combined_text, single_setting
from .shot_planner_pools import BODY_MODES, POSE_CATEGORIES, expression_options

WIDGET_TYPE = "ECLIPSE_NOVA_SHOT_PLANNER"
MAX_TEXT = 10000
MAX_MANUAL = 1024 * 1024
NUMBERS = {
    "count": number("Count", 40, 1, MAX_SHOTS),
    "manual_start": number("Start entry", 1, 1, 2**31 - 1),
    "pose_cooldown": number("Pose", 3, 0, 20),
    "expression_cooldown": number("Expression", 3, 0, 20),
    "camera_cooldown": number("Camera", 2, 0, 20),
}
CHOICES = {
    "body_mode": {key: key.title() for key in ("any", *BODY_MODES)},
    "pose_category": {key: key.title() for key in ("all", *POSE_CATEGORIES)},
    "selection": {key: key.title() for key in ("balanced", "close", "mid", "wide")},
    "stop_when": {"poses": "Poses covered", "expressions": "Expressions covered",
                  "poses_and_expressions": "Poses & expressions covered", "cameras": "Cameras used", "never": "Never"},
}
TEXTS = {
    "character_lock": ("Character", "The same character as the reference images; preserve facial identity, hair and body proportions."),
    "outfit_lock": ("Outfit", ""),
    "scene": ("Scene", "An uninterrupted featureless white background and light floor, soft natural light."),
    "choices": ("Candidate choices", ""),
    "manual_shots": ("Manual shots", ""),
}
TIPS = {
    "project": "Shared reservation history in Planner mode. Manual uses this label for stable per-entry seeds and never accesses history.",
    "batch_id": "Unchanged settings replay a reserved batch. Changed settings create a numbered variant. Keep this ID fixed across manual ranges to preserve each entry's seed.",
    "count": "Maximum selected prompts, not completed images. Final coverage and manual batches can be shorter. Planner reserves three candidates per selected shot.",
    "manual_start": "First nonempty entry, starting at 1. For count 25 use starts 1, 26, 51. Entries never wrap; IDs and seeds keep their absolute positions.",
    "character_lock": "Identity and reference-role instructions added to each shot. Connect Character Sheet Pack's positive output here. Text lists are combined into one shared lock.",
    "outfit_lock": "Shared wardrobe instructions. Leave empty if Character already specifies the outfit. Connected text lists combine into one shared lock.",
    "scene": "Shared background and lighting instructions added to every shot. Connected text lists are combined.",
    "manual_shots": "One shot per nonempty line. A connected string or flat STRING list overrides this field. Keeps order and duplicates, then adds Character, Outfit and Scene to each shot.",
    "choices": "Optional close/mid/wide per requested shot, separated by commas or newlines. Overrides Output distance. Exactly Count values are required.",
    "body_mode": "Posture filter, combined with pose category. Restricted pools may require lower cooldowns.",
    "pose_category": "Activity filter from the editable pose pool. Does not change wardrobe, expression or scene.",
    "selection": "Balanced favors the least-used distance. A fixed distance selects that candidate; all three candidates are still planned.",
    "expression": "Random uses distinct expressions with cooldowns. A fixed expression uses it for every candidate. Off omits expression wording. Reload planner files after edits.",
    "stop_when": "Selected-output coverage. Reserve stops automatic queueing when complete; Preview starts from empty history and reports capacity. Never keeps cycling.",
    "pose_cooldown": "Number of previous selected poses excluded from new candidates, including prior batches. Zero allows reuse between sets.",
    "expression_cooldown": "Previous selected expressions excluded in Random mode. Fixed expressions and Off ignore this setting.",
    "camera_cooldown": "Previous camera families excluded. Non-camera coverage modes may relax this cooldown to finish coverage, with a warning.",
}


def default_configuration():
    return {"version": 1, "mode": "Planner",
            "parameters": {"project": "my-character", "batch_id": "batch-001",
                           **{key: spec["default"] for key, spec in NUMBERS.items()},
                           "body_mode": "any", "pose_category": "all", "selection": "balanced",
                           "expression": "random", "stop_when": "poses", "operation": "reserve"},
            "texts": {key: default for key, (_, default) in TEXTS.items()},
            "seed": {"source": "local", "value": "0", "policy": "fixed"}}


def editor_spec():
    return copy.deepcopy({"numbers": NUMBERS, "choices": CHOICES, "texts": TEXTS, "tips": TIPS,
                          "expressions": expression_options(), "maxText": MAX_TEXT, "maxManual": MAX_MANUAL})


def _text(value, label, maximum):
    if not isinstance(value, str) or len(value) > maximum or "\0" in value:
        raise ValueError(f"{label} must be text of at most {maximum} characters without NUL characters.")
    return value


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 8 * 1024 * 1024:
        raise ValueError("Shot Planner configuration must be JSON text smaller than 8 MiB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid Shot Planner configuration JSON.") from error
    require_fields(config, ("version", "mode", "parameters", "texts", "seed"))
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 Shot Planner configuration.")
    require_choice(config["mode"], ("Planner", "Manual"), "Mode")
    p = config["parameters"]
    require_fields(p, (*NUMBERS, *CHOICES, "project", "batch_id", "expression", "operation"), name="Planner settings")
    _text(p["project"], "Project", 200)
    if not p["project"].strip():
        raise ValueError("Project must not be empty.")
    if not isinstance(p["batch_id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", p["batch_id"]):
        raise ValueError("Batch ID must be 1–80 letters, digits, underscores, dots or hyphens, starting with a letter or digit.")
    for key, spec in NUMBERS.items():
        require_number(p[key], spec)
    for key, choices in CHOICES.items():
        require_choice(p[key], choices, key.replace("_", " ").title())
    require_choice(p["operation"], ("reserve", "preview"), "Operation")
    # Membership belongs to allocation, not validation: old reservations replay
    # their saved expression even after its ID has been removed from the files.
    if not isinstance(p["expression"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", p["expression"]):
        raise ValueError("Expression must be random, off or an expression ID.")
    require_fields(config["texts"], TEXTS, name="Planner texts")
    for key, value in config["texts"].items():
        _text(value, TEXTS[key][0], MAX_MANUAL if key == "manual_shots" else MAX_TEXT)
    seed = config["seed"]
    require_fields(seed, ("source", "value", "policy"), name="Seed")
    require_choice(seed["source"], ("local", "input"), "Seed source")
    require_choice(seed["policy"], ("fixed", "random", "increment", "decrement"), "Seed policy")
    if (not isinstance(seed["value"], str) or not re.fullmatch(r"0|[1-9][0-9]{0,19}", seed["value"])
            or int(seed["value"]) >= 2**64):
        raise ValueError("Seed must be an unsigned 64-bit decimal value.")
    return config


def _none(value):
    return value is None or (isinstance(value, list) and len(value) == 1 and value[0] is None)


def resolve_inputs(config, project=None, character_lock=None, outfit_lock=None, scene=None, manual_shots=None, seed_input=None):
    p = config["parameters"]
    name = p["project"] if _none(project) else single_setting(project, "project")
    _text(name, "Project", 200)
    if not name.strip():
        raise ValueError("Project must not be empty.")
    settings = {"project": name, "batch_id": p["batch_id"], "count": int(p["count"]), "mode": config["mode"]}
    for key, value in (("character_lock", character_lock), ("outfit_lock", outfit_lock), ("scene", scene)):
        settings[key] = _text(config["texts"][key] if _none(value) else combined_text(value, key), TEXTS[key][0], MAX_TEXT)
    if config["seed"]["source"] == "input" and not _none(seed_input):
        seed = single_setting(seed_input, "seed_input")
        if type(seed) is not int or not 0 <= seed < 2**64:
            raise ValueError("seed_input must contain one unsigned 64-bit integer.")
    else:
        seed = secrets.randbits(64) if config["seed"]["policy"] == "random" else int(config["seed"]["value"])
    settings["seed"] = seed
    if config["mode"] == "Manual":
        settings["manual_start"] = int(p["manual_start"])
        settings["manual_shots"] = config["texts"]["manual_shots"] if _none(manual_shots) else manual_shots
    else:
        settings.update({key: p[key] for key in (*CHOICES, "expression", "operation")})
        settings.update({key: int(p[key]) for key in ("pose_cooldown", "expression_cooldown", "camera_cooldown")})
        settings["choices"] = config["texts"]["choices"]
    return settings
