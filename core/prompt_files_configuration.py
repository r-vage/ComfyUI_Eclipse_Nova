# Configuration contracts for the two prompt-file panels.

import json

READ_WIDGET = "ECLIPSE_NOVA_READ_PROMPT_FILES"
SAVE_WIDGET = "ECLIPSE_NOVA_SAVE_PROMPT"
PLACEHOLDERS = "Placeholders: %source_filename, %source_folder, %source_base_folder, %counter, %today, %date, %time, %Y, %y, %m/%M, %d/%D, %H, %S."
READ_FIELDS = [
    {"key": "stop_at_end", "label": "Stop at end", "section": "mode", "default": True,
     "tooltip": "Stop Next, Previous or Shuffle at the boundary. Disable to repeat the sequence."},
    {"key": "log_prompt", "label": "Log", "section": "mode", "default": False,
     "tooltip": "Write the selected prompt to the server console."},
    {"key": "file_paths", "label": "File paths", "section": "files", "default": "", "multiline": True,
     "maxLength": 65536, "tooltip": "One text file per line. Quoted paths are accepted. Non-empty lines are combined in file order."},
    {"key": "index", "label": "Index", "section": "selection", "default": 0, "min": 0, "max": 2147483647,
     "tooltip": "Zero-based index. Next and Previous start here; fixed indices outside the list use the nearest available line."},
    {"key": "advance", "label": "After run", "section": "selection", "default": "fixed",
     "options": ["fixed", "random", "next", "previous", "shuffle"],
     "tooltip": "Fixed, random, forward, backward, or shuffle without repeats. Advances only when the node executes; an unchanged seed_input freezes the selection."},
    {"key": "revision", "label": "Revision", "section": "internal", "default": 0, "min": 0, "max": 2147483647},
]
SAVE_FIELDS = [
    {"key": "save_to_disk", "label": "Save", "section": "mode", "default": True,
     "tooltip": "Save prompt files. Disable to pass text through without writing files."},
    {"key": "use_source_folder", "label": "Source folder", "section": "mode", "default": True,
     "tooltip": "Resolve relative output paths beside the source file from pipe_opt or filename_opt. Without a source, use ComfyUI output."},
    {"key": "log_prompt", "label": "Log", "section": "mode", "default": False,
     "tooltip": "Write saved prompt text to the server console."},
    {"key": "output_path", "label": "Output path", "section": "output", "default": "", "wide": True,
     "tooltip": "Empty saves beside the source when Source folder is enabled, otherwise in ComfyUI output. Absolute paths are supported. Pipe output_path takes priority. " + PLACEHOLDERS},
    {"key": "filename_prefix", "label": "Filename prefix", "section": "output", "default": "%source_filename", "wide": True,
     "tooltip": "Use %source_filename to pair captions with images. Pipe filename_prefix takes priority. " + PLACEHOLDERS},
    {"key": "filename_delimiter", "label": "Delimiter", "section": "output", "default": "_", "maxLength": 32,
     "tooltip": "Separates the prefix and counter in New mode."},
    {"key": "filename_number_padding", "label": "Counter digits", "section": "output", "default": 4, "min": 1, "max": 9},
    {"key": "extension", "label": "Format", "section": "format", "default": "txt", "options": ["txt", "csv", "json"]},
    {"key": "write_mode", "label": "Write mode", "section": "format", "default": "new",
     "options": ["new", "overwrite", "append", "append_batch", "keep"],
     "tooltip": "New numbers duplicates; Overwrite replaces; Append adds entries; Append batch keeps the file open until idle; Keep skips existing files."},
    {"key": "csv_positive_name", "label": "Style name", "section": "format", "default": "✅Style", "formats": ["csv"], "wide": True},
    {"key": "csv_negative_prompt", "label": "Negative prompt", "section": "format",
     "default": "ugly, deformed, noisy, low poly, blurry, painting", "formats": ["csv"], "multiline": True, "maxLength": 65536},
    {"key": "nsfw_level", "label": "Content rating", "section": "format", "default": "disabled", "formats": ["json"],
     "options": ["disabled", "auto", "None", "Mature", "X"], "tooltip": "Optional JSON nsfwLevel. Auto uses the shared content-rating patterns."},
]


def editor_spec(kind):
    return {"kind": kind, "fields": READ_FIELDS if kind == "read" else SAVE_FIELDS,
            "sections": {"files": "Files", "selection": "Selection"} if kind == "read" else {"output": "Output", "format": "Format"}}


def default_configuration(kind):
    return {"version": 1, "options": {field["key"]: field["default"] for field in editor_spec(kind)["fields"]}}


def validate_configuration(raw, kind):
    if not isinstance(raw, str) or len(raw) > 524288:
        raise ValueError("Prompt-file configuration must be a JSON string of at most 524288 characters.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid prompt-file configuration JSON.") from error
    if not isinstance(config, dict) or set(config) != {"version", "options"}:
        raise ValueError("Prompt-file configuration has missing or unsupported fields.")
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Expected version 1 prompt-file configuration.")
    fields = editor_spec(kind)["fields"]
    options = config["options"]
    if not isinstance(options, dict) or set(options) != {field["key"] for field in fields}:
        raise ValueError("Prompt-file options have missing or unsupported fields.")
    for field in fields:
        value = options[field["key"]]
        if type(value) is not type(field["default"]):
            raise ValueError(f"Invalid {field['label']}.")
        if "min" in field and not field["min"] <= value <= field["max"]:
            raise ValueError(f"{field['label']} must be between {field['min']} and {field['max']}.")
        if "options" in field and value not in field["options"]:
            raise ValueError(f"Unsupported {field['label']}.")
        if isinstance(value, str) and ("\0" in value or len(value) > field.get("maxLength", 4096)):
            raise ValueError(f"Invalid {field['label']} text.")
    return config
