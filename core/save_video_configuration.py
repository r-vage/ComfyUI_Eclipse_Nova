# Structured video-save settings and per-pipe output controls.

import json
import math
import os

WIDGET_TYPE = "ECLIPSE_NOVA_SAVE_VIDEO"
PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
TRIM_MODES = ["none", "video_to_audio", "audio_to_video", "shortest", "loop_match", "loop_match_blend"]
METRICS = ["ncc", "mse", "luminance_mse", "gradient_mse"]
FIELDS = [
    {"key": "show_preview", "label": "Preview", "section": "mode", "default": True,
     "tooltip": "Show the saved video below the controls. Saving remains enabled."},
    {"key": "enable_trim", "label": "Trim", "section": "mode", "default": True,
     "tooltip": "Apply duration trimming or loop matching to IMAGE frames. Native VIDEO and explicit timing keep their source cadence."},
    {"key": "output_path", "label": "Output path", "section": "output", "default": "", "maxLength": 4096,
     "tooltip": "Empty uses ComfyUI output. Relative folders, absolute destinations and placeholders are supported. Pipe output_path, then path, takes priority."},
    {"key": "filename_prefix", "label": "Filename prefix", "section": "output", "default": "video/ComfyUI_Eclipse_Nova", "maxLength": 4096,
     "tooltip": "Name or nested path, with %today, %time, %model, %basemodel, %seed, %sampler_name, %scheduler, %steps, %cfg, %denoise and %clip_skip placeholders. Pipe filename_prefix takes priority."},
    {"key": "fps", "label": "FPS", "section": "encoding", "default": 24.0, "min": 1, "max": 240, "step": 0.1,
     "tooltip": "IMAGE frame rate. Pipe fps takes priority. VIDEO, exact timelines and timing_opt keep their own timing."},
    {"key": "crf", "label": "CRF", "section": "encoding", "default": 19, "min": 0, "max": 51, "step": 1,
     "tooltip": "H.264 quality factor. Lower values give higher quality and larger files."},
    {"key": "preset", "label": "Preset", "section": "encoding", "default": "veryfast", "options": PRESETS,
     "tooltip": "Compression speed: slower presets spend more time reducing file size."},
    {"key": "trim_mode", "label": "Trim mode", "section": "trim", "default": "video_to_audio", "options": TRIM_MODES},
    {"key": "loop_search_pct", "label": "Search %", "section": "trim", "default": 50, "min": 1, "max": 99, "step": 1},
    {"key": "loop_metric", "label": "Metric", "section": "trim", "default": "ncc", "options": METRICS},
    {"key": "loop_trim_start", "label": "Trim start", "section": "trim", "default": False,
     "tooltip": "Search both the beginning and end for the closest loop pair."},
    {"key": "loop_blend_frames", "label": "Blend frames", "section": "trim", "default": 8, "min": 0, "max": 60, "step": 1},
    {"key": "embed_workflow", "label": "Embed workflow", "section": "metadata", "default": True,
     "tooltip": "Embed the complete ComfyUI prompt and workflow as MP4 container metadata."},
    {"key": "save_generation_data", "label": "Generation data", "section": "metadata", "default": True,
     "tooltip": "Embed A1111-style generation parameters from pipe_opt, with available model, VAE, LoRA and embedding hashes."},
    {"key": "remove_prompts", "label": "Remove prompts", "section": "metadata", "default": False,
     "tooltip": "Blank prompts in generation parameters only. Embedded workflows and JSON sidecars retain their original text."},
    {"key": "add_loras_to_prompt", "label": "LoRA tags", "section": "metadata", "default": False,
     "tooltip": "Append pipe LoRA names and weights to the positive prompt in generation parameters."},
    {"key": "save_workflow_as_json", "label": "Workflow JSON", "section": "metadata", "default": False,
     "tooltip": "Write the workflow beside the MP4 as a JSON file."},
]


def default_configuration():
    return {"version": 1, "options": {field["key"]: field["default"] for field in FIELDS}}


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("Save Video configuration must be a JSON string of at most 16384 characters.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid Save Video configuration JSON.") from error
    if not isinstance(config, dict) or set(config) != {"version", "options"}:
        raise ValueError("Save Video configuration has missing or unsupported fields.")
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 Save Video configuration.")
    options = config["options"]
    if not isinstance(options, dict) or set(options) != {field["key"] for field in FIELDS}:
        raise ValueError("Save Video options have missing or unsupported fields.")
    for field in FIELDS:
        value = options[field["key"]]
        if isinstance(field["default"], float):
            valid = type(value) in (int, float) and math.isfinite(value)
        else:
            valid = type(value) is type(field["default"])
        if not valid:
            raise ValueError(f"Invalid value for {field['label']}.")
        if "min" in field and not field["min"] <= value <= field["max"]:
            raise ValueError(f"{field['label']} must be between {field['min']} and {field['max']}.")
        if "options" in field and value not in field["options"]:
            raise ValueError(f"Unsupported {field['label']}.")
        if isinstance(value, str) and ("\0" in value or len(value) > field.get("maxLength", 4096)):
            raise ValueError(f"Invalid {field['label']} text.")
    return config


def pipe_options(options, context, *, source_timing=False):
    # Resolve execution values without changing the saved local configuration.
    result = dict(options)
    context = context or {}
    path = context.get("output_path")
    if path is None:
        path = context.get("path")
    for key, value in (("output_path", path), ("filename_prefix", context.get("filename_prefix"))):
        if value is not None:
            if not isinstance(value, str) or "\0" in value or len(value) > 4096:
                raise ValueError(f"Pipe {key} must be a string of at most 4096 characters, or None.")
            result[key] = value
    if not source_timing:
        value = context.get("fps")
        if value is not None:
            if type(value) not in (int, float) or not math.isfinite(value) or not 1 <= value <= 240:
                raise ValueError("Pipe fps must be a finite number between 1 and 240, or None.")
            result["fps"] = float(value)
    return result


def output_directory(path, root, processor):
    if not path:
        return root
    return os.path.abspath(os.path.join(root, processor.process(path)))
