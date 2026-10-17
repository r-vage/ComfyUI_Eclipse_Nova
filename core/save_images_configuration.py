# Structured Save Images options. Rendering state is kept out of execution data.

import json

WIDGET_TYPE = "ECLIPSE_NOVA_SAVE_IMAGES"
FORMATS = ["png", "jpg", "jpeg", "gif", "tiff", "webp", "bmp"]
PLACEHOLDERS = "Placeholders: %today, %date, %time, %Y, %m/%M, %d/%D, %H, %S, %basemodel, %model, %seed, %sampler_name, %scheduler, %steps, %cfg, %denoise, %clip_skip."

FIELDS = [
    {"key": "save_to_disk", "label": "Save", "section": "mode", "default": True,
     "tooltip": "Save output files. Disable for temporary PNG previews only."},
    {"key": "show_previews", "label": "Preview", "section": "mode", "default": True,
     "tooltip": "Show saved images or temporary previews below the controls."},
    {"key": "use_output", "label": "Custom path", "section": "output", "default": True,
     "tooltip": "Use the path below; otherwise use the ComfyUI output directory. Pipe paths take priority either way."},
    {"key": "output_path", "label": "Output path", "section": "output", "default": r"%Y-%M-%D\%basemodel",
     "maxLength": 4096, "tooltip": "Relative to ComfyUI output, or an absolute directory. Pipe output_path, then path, takes priority. " + PLACEHOLDERS},
    {"key": "use_filename", "label": "Custom filename", "section": "output", "default": True,
     "tooltip": "Use the filename controls below; otherwise ComfyUI_0001. A pipe filename_prefix takes priority."},
    {"key": "filename_prefix", "label": "Filename prefix", "section": "output", "default": "%basemodel, %seed, %sampler_name, %scheduler, %steps_steps",
     "maxLength": 4096, "tooltip": "Optional subfolders must stay within the output path. Pipe filename_prefix takes priority. " + PLACEHOLDERS},
    {"key": "filename_delimiter", "label": "Delimiter", "section": "output", "default": "_", "maxLength": 32},
    {"key": "filename_number_padding", "label": "Counter digits", "section": "output", "default": 4, "min": 1, "max": 9},
    {"key": "filename_number_start", "label": "Counter first", "section": "output", "default": False},
    {"key": "extension", "label": "Format", "section": "format", "default": "png", "options": FORMATS},
    {"key": "optimize_image", "label": "Optimize", "section": "format", "default": False, "formats": ["png", "jpg", "jpeg"]},
    {"key": "lossless_webp", "label": "Lossless", "section": "format", "default": False, "formats": ["webp"]},
    {"key": "use_quality", "label": "Custom quality", "section": "format", "default": False, "formats": ["jpg", "jpeg", "webp"]},
    {"key": "quality", "label": "Quality", "section": "format", "default": 100, "min": 1, "max": 100, "formats": ["jpg", "jpeg", "webp"]},
    {"key": "use_dpi", "label": "Custom DPI", "section": "format", "default": False, "formats": ["jpg", "jpeg", "png", "tiff", "bmp"],
     "tooltip": "Write custom print resolution metadata. Pixel dimensions and image detail stay unchanged."},
    {"key": "dpi", "label": "DPI", "section": "format", "default": 300, "min": 1, "max": 2400, "formats": ["jpg", "jpeg", "png", "tiff", "bmp"]},
    {"key": "embed_workflow", "label": "Embed workflow", "section": "metadata", "default": True, "formats": ["png", "webp"],
     "tooltip": "Embed the complete prompt and workflow in PNG or WebP. Temporary PNG previews also support this."},
    {"key": "save_generation_data", "label": "Generation data", "section": "metadata", "default": True, "formats": ["png"],
     "tooltip": "Embed A1111-compatible generation parameters from pipe_opt in saved PNG files."},
    {"key": "remove_prompts", "label": "Remove prompts", "section": "metadata", "default": False, "formats": ["png"],
     "tooltip": "Remove prompt text from generation parameters only. Embedded workflows and JSON sidecars still contain their original text."},
    {"key": "add_loras_to_prompt", "label": "LoRA tags", "section": "metadata", "default": False, "formats": ["png"],
     "tooltip": "Append the pipe's LoRA tags to the positive prompt in generation parameters."},
    {"key": "save_workflow_as_json", "label": "Workflow JSON", "section": "metadata", "default": False,
     "tooltip": "Save a workflow JSON sidecar next to each output image, in any format."},
]


def default_configuration():
    return {"version": 1, "options": {field["key"]: field["default"] for field in FIELDS}}


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError("Save Images configuration must be a JSON string of at most 16384 characters.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid Save Images configuration JSON.") from error
    if not isinstance(config, dict) or set(config) != {"version", "options"}:
        raise ValueError("Save Images configuration has missing or unsupported fields.")
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 Save Images configuration.")
    options = config["options"]
    if not isinstance(options, dict) or set(options) != {field["key"] for field in FIELDS}:
        raise ValueError("Save Images options have missing or unsupported fields.")
    for field in FIELDS:
        value = options[field["key"]]
        if type(value) is not type(field["default"]):
            raise ValueError(f"Invalid value for {field['label']}.")
        if "min" in field and not field["min"] <= value <= field["max"]:
            raise ValueError(f"{field['label']} must be between {field['min']} and {field['max']}.")
        if "options" in field and value not in field["options"]:
            raise ValueError(f"Unsupported {field['label']}.")
        if isinstance(value, str) and ("\0" in value or len(value) > field.get("maxLength", 4096)):
            raise ValueError(f"Invalid {field['label']} text.")
    return config


def pipe_destination(context):
    if not context:
        return {}
    overrides = {}
    path = context.get("output_path")
    if path is None:
        path = context.get("path")
    for key, value in (("output_path", path), ("filename_prefix", context.get("filename_prefix"))):
        if value is not None:
            if not isinstance(value, str) or len(value) > 4096 or "\0" in value:
                raise ValueError(f"Pipe {key} must be a string of at most 4096 characters, or None.")
            overrides[key] = value
    return overrides
