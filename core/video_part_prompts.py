# Text-only review and immutable per-render-part edits for saved H3 runs.
import hashlib
import json
import math
from dataclasses import replace

from .minimax_h3_clips import H3ClipPlan
from .minimax_h3_prompts import segment_prompt
from .minimax_h3_segment_plan import validate_segment_plan
from .video_run import _contained_file, manifest_path

EDITS_TYPE = "ECLIPSE_PART_PROMPT_EDITS"
WIDGET_TYPE = "ECLIPSE_NOVA_PART_PROMPTS"


def default_configuration():
    return {"version": 1, "enabled": False, "source": "", "edits": {}}


def validate_configuration(raw):
    if not isinstance(raw, str) or len(raw) > 1048576:
        raise ValueError("Part prompt configuration must be JSON text under 1 MiB.")
    value = json.loads(raw)
    if (not isinstance(value, dict) or set(value) != {"version", "enabled", "source", "edits"}
            or value["version"] != 1 or type(value["enabled"]) is not bool
            or not isinstance(value["source"], str) or len(value["source"]) > 128
            or not isinstance(value["edits"], dict) or len(value["edits"]) > 1000):
        raise ValueError("Invalid version 1 part prompt configuration.")
    for part, prompt in value["edits"].items():
        if not part.isascii() or not part.isdigit() or not 1 <= int(part) <= 1000000 or str(int(part)) != part:
            raise ValueError("Prompt edits use one-based part numbers.")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 65536:
            raise ValueError(f"Part {part}: enter replacement text, or reset this edit.")
    if value["enabled"] and value["edits"] and not value["source"]:
        raise ValueError("Read the selected run's prompts before enabling edits.")
    return value


def source_key(value):
    source = value.get("prompt_source_id")
    if source is None:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if not isinstance(source, str) or not source or len(source) > 128:
        raise ValueError("Invalid saved prompt source identifier.")
    return source


def prompt_catalog(run_path):
    # Reading this catalog never loads saved references, audio or video arrays.
    root = manifest_path(str(run_path)).parent
    manifest = json.loads((root / "run.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("format") != "eclipse_video_run" or manifest.get("checkpoint") != "checkpoint.json":
        raise ValueError("This run has no saved input checkpoint. Select a run created with Video Loop Start.")
    path = _contained_file(root, "checkpoint.json")
    if path.stat().st_size > 32 * 1048576:
        raise ValueError("The saved prompt plan exceeds the 32 MiB review limit.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("format") != "eclipse_render_checkpoint" or value.get("version") != 1:
        raise ValueError("Unsupported render checkpoint.")
    plan = value["plan"]
    if value["kind"] == "clips":
        items = [(c["start"], c["keep"], c["prompt"]) for c in plan["clips"]]
    elif value["kind"] == "frames":
        plan, tasks = validate_segment_plan(plan)
        items = [(t["output_start_frame"], t["keep_frames"], segment_prompt(
            value["prompts"], t["prompt_index"], value["first_part_prompt"], plan, t)) for t in tasks]
    else:
        raise ValueError("Unsupported saved run kind.")
    fps = value["fps"]
    if (not isinstance(fps, (int, float)) or not math.isfinite(fps) or fps <= 0 or not items
            or any(type(start) is not int or type(count) is not int or start < 0 or count < 1
                   or not isinstance(text, str) for start, count, text in items)):
        raise ValueError("Invalid saved part timing or prompt text.")
    return {"source": source_key(value), "run": str(root), "completed": len(manifest["chunks"]),
            "parts": [{"part": i + 1, "start": start / fps, "end": (start + count) / fps, "prompt": text}
                      for i, (start, count, text) in enumerate(items)]}


def apply_prompt_edits(data, edits, start):
    if not edits or not edits["enabled"] or not edits["edits"]:
        return data
    if edits["source"] != data.prompt_source_id:
        raise ValueError("Prompt edits belong to another run. Read the selected run's prompts or disable Apply edits.")
    native = isinstance(data.plan, H3ClipPlan)
    parts = list(data.plan.clips if native else data.plan["tasks"])
    for number, text in edits["edits"].items():
        index = int(number) - 1
        if index >= len(parts):
            raise ValueError(f"Prompt edit part {number} is outside this run's plan.")
        part = parts[index]
        current = part.prompt if native else segment_prompt(
            data.prompts, part["prompt_index"], data.first_part_prompt, data.plan, part)
        if current == text:
            continue  # An edited revision can continue with the same editor still enabled.
        if index < start:
            raise ValueError(f"Part {number} is being retained. Set Restart part to {number} or earlier to change its prompt.")
        parts[index] = replace(part, prompt=text) if native else {**part, "prompt_override": text}
    plan = replace(data.plan, clips=tuple(parts)) if native else {**data.plan, "tasks": parts}
    return replace(data, plan=plan)
