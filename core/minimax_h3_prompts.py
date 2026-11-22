# Shared final text resolution for conditioning and saved-part prompt review.
import re

from .minimax_h3_segment_plan import (
    task_uses_intentional_camera_cut,
    technical_cut_prompt_for_task,
)

_VISUAL_LABEL = re.compile(r"^\s*integrated_multimodal_description[ \t]*:", re.IGNORECASE)
_AUDIO_LABEL = re.compile(r"^[ \t]*(overall_soundscape|non_diegetic_music)[ \t]*:[ \t]*", re.MULTILINE | re.IGNORECASE)


def generation_prompt(scene, global_prompt, *, supplied_audio):
    """Assemble the editable prompt after scene observation and optional rewriting."""
    direction = global_prompt.strip()
    audio_fields = list(_AUDIO_LABEL.finditer(scene))
    boundary = audio_fields[0].start() if audio_fields else len(scene)
    visual = scene[:boundary].rstrip()
    visual_end = len(visual)
    structured = _VISUAL_LABEL.match(visual)
    if not structured and not supplied_audio:
        return "\n\n".join(part for part in (direction, scene) if part.strip())

    if supplied_audio and not structured:
        action = visual.strip()
        if not action.startswith("[Shot 1]"):
            action = f"[Shot 1] {action}".rstrip()
        visual = f"integrated_multimodal_description: {action}"
    if direction and not re.search(r"(?<!\w)" + re.escape(direction) + r"(?!\w)", visual):
        visual = f"{visual} {direction}"
    if not supplied_audio:
        return visual + scene[visual_end:]

    music = "N/A"
    for index, field in enumerate(audio_fields):
        if field[1].lower() == "non_diegetic_music":
            end = audio_fields[index + 1].start() if index + 1 < len(audio_fields) else len(scene)
            music = scene[field.end():end].strip() or music
            break
    return f"{visual}\n\noverall_soundscape: N/A\n\nnon_diegetic_music: {music}"


def prompt_items(value):
    result = []

    def collect(item):
        if isinstance(item, (list, tuple)):
            for child in item:
                collect(child)
        elif isinstance(item, str):
            result.extend(line.strip() for line in item.splitlines() if line.strip())

    collect(value)
    return result or [""]


def segment_prompt(prompts, prompt_index, first_part_prompt="", plan=None, task=None):
    if task is not None and "prompt_override" in task:
        override = task["prompt_override"]
        if not isinstance(override, str) or not override.strip():
            raise ValueError("Part prompt override must be nonblank text.")
        return override
    if plan is not None and "reviewed_prompts" in plan:
        return plan["reviewed_prompts"][prompt_index]
    lines = prompt_items(prompts)
    selected = lines[prompt_index] if 0 <= prompt_index < len(lines) else lines[0]
    opening = bool(first_part_prompt.strip())
    if task is not None and opening and "image_part_directions" in plan:
        directions = plan["image_part_directions"]
        owner = task["source_image_index"]
        direction = directions[(owner - 1) % len(directions)] if owner > 0 and directions else first_part_prompt
        # Image changes and capacity splits inside an image interval retain the
        # matching scene direction. Older saved plans keep their prior contract.
        return f"{selected.rstrip()} {' '.join(direction.split())}".strip()
    if task is not None:
        cut = task_uses_intentional_camera_cut(plan, task)
        opening = opening and task["source_image_index"] == 0 and not cut
        if cut:
            selected = f"{selected.rstrip()} {technical_cut_prompt_for_task(plan, task)}".strip()
    if opening:
        selected = f"{selected.rstrip()} {' '.join(first_part_prompt.split())}".strip()
    return selected
