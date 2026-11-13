# Shared final text resolution for conditioning and saved-part prompt review.
from .minimax_h3_segment_plan import (
    task_uses_intentional_camera_cut,
    technical_cut_prompt_for_task,
)


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
