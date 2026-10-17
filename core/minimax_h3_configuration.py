# Named configurations for MiniMax H3 panels; connected values override local fields.
import copy
import json

from .image_helpers import unwrap_value
from .minimax_h3_segment_plan import (
    DEFAULT_TECHNICAL_CUT_INSTRUCTION,
    is_h3_frame_count,
)
from .resolution_sizing import number, require_choice, require_fields, require_number

WIDGET_TYPE = "ECLIPSE_NOVA_MINIMAX_H3"
MAX_TEXT = 262144
TITLES = {
    "segmented_timeline": "MiniMax H3 Audio Timeline Planner",
    "segmented_step": "MiniMax H3 Audio Plan Step",
    "segmented_conditioning": "MiniMax H3 Segmented Conditioning",
}
NUMBERS = {
    "max_render_frames": number("Max render frames", 362, 124, 362, 17),
    "warmup_seconds": number("Warmup seconds", 2.0, 0, 10, 0.01),
    "search_window_seconds": number("Search radius (seconds)", 5.0, 0, 10, 0.05),
    "min_gap_duration": number("Minimum gap (seconds)", 0.25, 0.02, 5, 0.01),
    "resume_hold_duration": number("Resume hold (seconds)", 0.15, 0.02, 5, 0.01),
    "task_index": number("Task index", 0, 0, 65535),
    "prompt_index": number("Prompt index", 0, 0, 65535),
    "width": number("Width", 1344, 32, 16384, 32),
    "height": number("Height", 768, 32, 16384, 32),
    "start_guide_frame_index": number("Start frame", 0, -1, 4096),
    "endpoint_frame_index": number("Endpoint frame", -1, -1, 4096),
    "visual_condition_strength": number("Visual strength", 0.999, 0, 1, 0.001),
}
CHOICES = {
    "conditioning_family": {"fl2va_keyframes": "FL2VA", "ref2va_active_reference": "Ref2VA"},
    "segment_strategy": {"warmup_reset": "Warm reset", "hard_cut": "Hard cut", "first_last_bridge": "Bridge"},
    "reset_anchor": {"first_only": "First only", "same_first_last_experimental": "First + last (experimental)"},
    "technical_split_source": {"original_image_reset": "Original image", "generated_continuation": "Generated continuity"},
    "ref_image_size": {"match": "Match canvas", "max": "Maximum"},
    "transition_edge": {"activity_resume": "Activity resume", "silence_start": "Silence start"},
    "technical_seam_style": {"plain_reset": "Plain reset", "intentional_camera_cut": "Camera cut"},
}
CHOICE_DEFAULTS = {key: next(iter(values)) for key, values in CHOICES.items()}
TEXTS = {
    "manual_transition_times": ("Transition times", ""),
    "technical_cut_instruction": ("Cut instructions", DEFAULT_TECHNICAL_CUT_INSTRUCTION),
    "prompts": ("Prompts", ""),
}
TOGGLES = {"align_to_activity_gap": ("Activity gaps", True), "has_start_guide": ("Start guide", True), "has_last_image": ("End guide", False)}
_ACTIVITY = ["align_to_activity_gap", "transition_edge", "search_window_seconds", "min_gap_duration", "resume_hold_duration"]
_CANVAS = ["width", "height"]
FIELDS = {
    "segmented_timeline": ["conditioning_family", "segment_strategy", "warmup_seconds", "reset_anchor", "technical_split_source", "ref_image_size", "manual_transition_times", "max_render_frames", *_ACTIVITY, "technical_seam_style", "technical_cut_instruction"],
    "segmented_step": ["task_index"],
    "segmented_conditioning": ["prompts", "prompt_index", "conditioning_family", "has_start_guide", "start_guide_frame_index", "has_last_image", "endpoint_frame_index", *_CANVAS, "ref_image_size", "visual_condition_strength"],
}
OVERRIDES = {
    "segmented_timeline": ["manual_transition_times", "technical_cut_instruction"],
    "segmented_step": ["task_index"],
    "segmented_conditioning": list(FIELDS["segmented_conditioning"]),
}
INTEGER_FIELDS = {"max_render_frames", "task_index", "prompt_index", "width", "height", "start_guide_frame_index", "endpoint_frame_index"}
LIST_TEXT_FIELDS = {"prompts", "technical_cut_instruction"}
TIPS = {
    "conditioning_family": "Choose the family matching your H3 checkpoint. FL2VA uses positional guides; Ref2VA uses only the active reference.",
    "segment_strategy": "Warm reset discards a lead-in. Hard cut retains the destination at the cut. Bridge hides its endpoint at the first discarded frame. Ref2VA supports warm reset only.",
    "warmup_seconds": "Discarded lead-in uses the preceding real guide audio. Hidden frames consume render capacity.",
    "reset_anchor": "First + last adds an experimental hidden same-source endpoint when no bridge destination exists. FL2VA only.",
    "technical_split_source": "Original image resets reduce recursive drift. Generated continuity uses the preceding 22 retained frames; FL2VA only.",
    "technical_seam_style": "Camera cut appends instructions only at same-image original reset tasks, with non-zero FL2VA warmup.",
    "technical_cut_instruction": "Non-empty prompts cycle across intentional technical cuts. A connected string or string list overrides local text. Blank uses the engine's default instruction.",
    "manual_transition_times": "Comma-separated seconds, one per image after the first. Blank distributes transitions evenly. Connected empty text clears local times.",
    "max_render_frames": "Legal H3 lengths are 124 through 362 in steps of 17. Warmup and hidden endpoints count toward this limit.",
    "align_to_activity_gap": "Use connected Wav2Vec features to align transitions and eligible technical seams. Without features the engine retains deterministic placements.",
    "transition_edge": "Place the transition at sustained activity resume or the start of a low-activity gap.",
    "search_window_seconds": "Search before and after each target transition in a multiple-image timeline.",
    "min_gap_duration": "Minimum low-activity duration accepted as a gap.",
    "resume_hold_duration": "Minimum sustained activity after a gap. Used for Activity resume.",
    "task_index": "Zero-based plan task. A connected loop index overrides the local value; zero is valid.",
    "prompt_index": "Complete prompt owner from Plan Step. Out-of-list indexes use the first non-empty prompt.",
    "prompts": "One complete prompt per non-empty line or list entry. Connected prompt lists stay together for task selection.",
    "width": "Generation canvas width. A connected non-None integer overrides this local value.",
    "height": "Generation canvas height. A connected non-None integer overrides this local value.",
    "ref_image_size": "Ref2VA only: Match limits toward canvas area; Maximum permits a 2048-pixel short edge. Neither mode upscales.",
    "has_start_guide": "Use the source as a positional FL2VA start guide. Connect the flag from Plan Step.",
    "has_last_image": "Use last_image as a positional FL2VA endpoint. Connect the flag from Plan Step.",
    "start_guide_frame_index": "Local start guide frame; -1 when absent. Connect the corresponding Plan Step output.",
    "endpoint_frame_index": "Local endpoint frame; -1 when absent. Connect the corresponding Plan Step output.",
    "visual_condition_strength": "0.999 preserves native conditioning. 1 removes conditioning noise; lower values add seeded noise to VisualVAE conditioning. Audio and text tokens are unchanged.",
}


def default_configuration(kind):
    require_choice(kind, TITLES, "MiniMax tool")
    values = {**{k: v["default"] for k, v in NUMBERS.items()}, **CHOICE_DEFAULTS,
              **{k: v[1] for k, v in TEXTS.items()}, **{k: v[1] for k, v in TOGGLES.items()}}
    return {"version": 1, "kind": kind, "parameters": {key: values[key] for key in FIELDS[kind]}}


def editor_spec(kind):
    keys = FIELDS[kind]
    return copy.deepcopy({"kind": kind, "title": TITLES[kind], "keys": keys,
                          "numbers": {k: v for k, v in NUMBERS.items() if k in keys},
                          "choices": {k: v for k, v in CHOICES.items() if k in keys},
                          "texts": {k: v for k, v in TEXTS.items() if k in keys},
                          "toggles": {k: v[0] for k, v in TOGGLES.items() if k in keys},
                          "tips": TIPS, "overrides": OVERRIDES[kind], "maxText": MAX_TEXT})


def _text(value, key, allow_list=False):
    if allow_list and isinstance(value, (list, tuple)):
        return [_text(item, key, True) for item in value]
    if not isinstance(value, str) or len(value) > MAX_TEXT or "\0" in value:
        raise ValueError(f"{key} must be text of at most {MAX_TEXT} characters without NUL characters.")
    return value


def _parameter(key, value, allow_list=False):
    if key in NUMBERS:
        require_number(value, NUMBERS[key])
        if key in INTEGER_FIELDS:
            if int(value) != value:
                raise ValueError(f"{key} must be an integer.")
            value = int(value)
        if key == "max_render_frames" and not is_h3_frame_count(value):
            raise ValueError("Max render frames must be 124 through 362 in steps of 17.")
    elif key in CHOICES:
        require_choice(value, CHOICES[key], key)
    elif key in TOGGLES:
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be boolean.")
    else:
        value = _text(value, key, allow_list)
    return value


def validate_configuration(raw, kind):
    raw = unwrap_value(raw)
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 4 * 1024 * 1024:
        raise ValueError("MiniMax configuration must be JSON text under 4 MiB.")
    c = json.loads(raw)
    require_fields(c, ("version", "kind", "parameters"))
    if type(c["version"]) is not int or c["version"] != 1 or c["kind"] != kind:
        raise ValueError(f"Expected version 1 {TITLES[kind]} configuration.")
    require_fields(c["parameters"], FIELDS[kind])
    c["parameters"] = {k: _parameter(k, v) for k, v in c["parameters"].items()}
    return c


def resolved_parameters(raw, kind, **overrides):
    parameters = validate_configuration(raw, kind)["parameters"]
    for key, value in overrides.items():
        if key not in OVERRIDES[kind]:
            raise ValueError(f"Unsupported {kind} override: {key}")
        # ComfyUI list-mode scalar inputs arrive wrapped. Prompt lists must stay whole.
        if key not in LIST_TEXT_FIELDS:
            value = unwrap_value(value)
        elif isinstance(value, (list, tuple)) and len(value) == 1 and value[0] is None:
            value = None
        if value is not None:
            parameters[key] = _parameter(key, value, key in LIST_TEXT_FIELDS)
    return parameters
