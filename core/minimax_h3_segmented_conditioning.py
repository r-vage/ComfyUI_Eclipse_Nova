# MiniMax H3 Segmented Conditioning [Eclipse Nova]
#
# Builds either native-style FL2VA positional conditioning or one persistent
# Ref2VA active-image reference. The families are deliberately exclusive.

import math
from typing import Any

import comfy.utils  # type: ignore
import node_helpers  # type: ignore
import torch  # type: ignore
from comfy_api.latest import io  # type: ignore

from .image_helpers import flatten_images
from .minimax_h3_segment_plan import (
    CONDITIONING_FAMILIES,
    REF_IMAGE_SIZES,
    task_uses_intentional_camera_cut,
    technical_cut_prompt_for_task,
    validate_segment_plan,
)

_CANVAS_MULTIPLE = 32
_REF_IMAGE_SHORT_EDGE = 2048
_NATIVE_VISUAL_CONDITION_STRENGTH = 0.999


def _single(value: Any, default: Any = None) -> Any:
    while isinstance(value, (list, tuple)):
        if not value:
            return default
        value = value[0]
    return default if value is None else value


def _prompt_items(value: Any) -> list[str]:
    prompts: list[str] = []

    def collect(item: Any) -> None:
        if isinstance(item, (list, tuple)):
            for child in item:
                collect(child)
        elif isinstance(item, str):
            prompts.extend(line.strip() for line in item.splitlines() if line.strip())

    collect(value)
    return prompts or [""]


def _visual_strength(value: Any) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not 0.0 <= value <= 1.0
    ):
        raise ValueError("visual_condition_strength must be from 0.0 to 1.0.")
    return float(value)


def _one_image(value: Any, name: str) -> torch.Tensor:
    images = flatten_images(value)
    if not images:
        raise ValueError(f"{name} must contain one IMAGE.")
    return images[0]


def _resize(image: torch.Tensor, width: int, height: int, crop: str) -> torch.Tensor:
    frame = image[:1, ..., :3].movedim(-1, 1)
    return comfy.utils.common_upscale(
        frame, width, height, "lanczos", crop
    ).movedim(1, -1)


def _reference_geometry(
    image: torch.Tensor,
    width: int,
    height: int,
    ref_image_size: str,
) -> tuple[int, int]:
    source_height, source_width = image.shape[1:3]
    if source_height < 1 or source_width < 1:
        raise ValueError("source_image has invalid dimensions.")
    if ref_image_size == "match":
        scale = min(
            1.0,
            math.sqrt((width * height) / (source_width * source_height)),
        )
    else:
        scale = min(1.0, _REF_IMAGE_SHORT_EDGE / min(source_width, source_height))
    target_width = max(
        _CANVAS_MULTIPLE,
        round(source_width * scale / _CANVAS_MULTIPLE) * _CANVAS_MULTIPLE,
    )
    target_height = max(
        _CANVAS_MULTIPLE,
        round(source_height * scale / _CANVAS_MULTIPLE) * _CANVAS_MULTIPLE,
    )
    return target_width, target_height


def _technical_cut_text(plan: dict[str, Any], task: dict[str, Any]) -> str:
    # The model sees a local clip, not the caller's crop. Put its camera change
    # early in the discarded prefix and leave the rest of that prefix to settle.
    visible_seconds = task["crop_start_frames"] / plan["fps"]
    cut_seconds = min(1.0, visible_seconds / 3.0)
    cut_time = f"{int(cut_seconds // 60):02d}:{cut_seconds % 60:06.3f}"
    # Do not expose the retained-range timestamp: H3 can turn even a negated
    # reference to that time into a second, visible camera cut.
    return (
        f"{technical_cut_prompt_for_task(plan, task)}\n"
        "Camera timing within this clip:\n"
        "[Shot 1] Begin in the opening composition of <Picture 1>, with the "
        "ongoing performance following the supplied audio.\n"
        f"[Shot 2] At {cut_time}, the camera cuts to the new framing described "
        "above. Complete the change of both angle and shot size at this cut, "
        "then maintain the established framing as one uninterrupted moving shot "
        "for the remainder of the clip. The performance and supplied audio "
        "continue uninterrupted across "
        "the camera cut. Lip movement follows the current supplied audio without "
        "restarting the vocal phrase; retain the main prompt's behavior during "
        "instrumental passages and silence."
    )


def encode_segment(
    clip,
    vae,
    prompts,
    prompt_index,
    conditioning_family,
    source_image,
    has_start_guide,
    start_guide_frame_index,
    has_last_image,
    endpoint_frame_index,
    width,
    height,
    ref_image_size,
    last_image=None,
    segment_plan=None,
    task_index=None,
    visual_condition_strength=_NATIVE_VISUAL_CONDITION_STRENGTH,
):
    clip = _single(clip)
    vae = _single(vae)
    prompt_index = _single(prompt_index, 0)
    conditioning_family = _single(
        conditioning_family, "fl2va_keyframes"
    )
    has_start_guide = _single(has_start_guide, True)
    start_guide_frame_index = _single(start_guide_frame_index, 0)
    has_last_image = _single(has_last_image, False)
    endpoint_frame_index = _single(endpoint_frame_index, -1)
    width = _single(width, 1344)
    height = _single(height, 768)
    ref_image_size = _single(ref_image_size, "match")
    segment_plan = _single(segment_plan)
    task_index = _single(task_index)
    visual_condition_strength = _visual_strength(
        _single(
            visual_condition_strength,
            _NATIVE_VISUAL_CONDITION_STRENGTH,
        )
    )
    source = _one_image(source_image, "source_image")

    if clip is None or vae is None:
        raise ValueError("clip and vae are required.")
    if not isinstance(prompt_index, int) or isinstance(prompt_index, bool):
        raise TypeError("prompt_index must be an integer.")
    if conditioning_family not in CONDITIONING_FAMILIES:
        raise ValueError(f"Unsupported conditioning_family: {conditioning_family}")
    if ref_image_size not in REF_IMAGE_SIZES:
        raise ValueError(f"Unsupported ref_image_size: {ref_image_size}")
    if not isinstance(has_start_guide, bool) or not isinstance(
        has_last_image, bool
    ):
        raise TypeError("Guide flags must be boolean.")
    if (
        not isinstance(start_guide_frame_index, int)
        or isinstance(start_guide_frame_index, bool)
        or not isinstance(endpoint_frame_index, int)
        or isinstance(endpoint_frame_index, bool)
    ):
        raise TypeError("Guide frame indices must be integers.")
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
        or width < 32
        or height < 32
    ):
        raise ValueError("width and height must be positive integer canvases.")

    prompt_lines = _prompt_items(prompts)
    selected_prompt = (
        prompt_lines[prompt_index]
        if 0 <= prompt_index < len(prompt_lines)
        else prompt_lines[0]
    )
    if segment_plan is None:
        if task_index is not None:
            raise ValueError("task_index requires segment_plan.")
    else:
        plan, tasks = validate_segment_plan(segment_plan)
        if not isinstance(task_index, int) or isinstance(task_index, bool):
            raise TypeError(
                "task_index must be an integer when segment_plan is connected."
            )
        if not 0 <= task_index < len(tasks):
            raise ValueError(
                f"task_index {task_index} is outside the plan's {len(tasks)} tasks."
            )
        task = tasks[task_index]
        if task["conditioning_family"] != conditioning_family:
            raise ValueError(
                "conditioning_family differs from the connected segment_plan task."
            )
        if task_uses_intentional_camera_cut(plan, task):
            selected_prompt = (
                f"{selected_prompt.rstrip()}\n"
                f"{_technical_cut_text(plan, task)}"
            ).strip()

    if conditioning_family == "ref2va_active_reference":
        if has_start_guide or has_last_image:
            raise ValueError(
                "Ref2VA cannot receive positional start or endpoint guides."
            )
        target_width, target_height = _reference_geometry(
            source, width, height, ref_image_size
        )
        resized = _resize(source, target_width, target_height, "disabled")
        prompt = selected_prompt
        if "<picture 1>" not in prompt.casefold():
            prompt = (
                "<Picture 1> is the active subject, appearance, and scene "
                f"reference. {prompt}"
            ).strip()
        ref_items = [{"type": "image", "data": resized}]
        tokens = clip.tokenize(prompt, minimax_ref_items=ref_items)
        conditioning = clip.encode_from_tokens_scheduled(tokens)
        latent = vae.encode(resized)
        ref_blocks = [
            {
                "kind": "image",
                "latent_h": target_height // 16,
                "latent_w": target_width // 16,
                "latent": latent,
            }
        ]
        conditioning_values = {"minimax_refs": ref_blocks}
        if visual_condition_strength != _NATIVE_VISUAL_CONDITION_STRENGTH:
            conditioning_values["minimax_visual_cond_noise_aug"] = (
                visual_condition_strength
            )
        conditioning = node_helpers.conditioning_set_values(
            conditioning, conditioning_values
        )
        return io.NodeOutput(conditioning)

    endpoint = None
    if has_last_image:
        endpoint = _one_image(last_image, "last_image")
        if endpoint_frame_index < 0:
            raise ValueError("FL2VA endpoint index must be non-negative.")
    elif endpoint_frame_index != -1:
        raise ValueError("endpoint_frame_index must be -1 when no endpoint exists.")
    if has_start_guide and start_guide_frame_index < 0:
        raise ValueError("FL2VA start-guide index must be non-negative.")
    if not has_start_guide and start_guide_frame_index != -1:
        raise ValueError(
            "start_guide_frame_index must be -1 when no start guide exists."
        )

    first = _resize(source, width, height, "disabled")
    token_images = [first]
    keyframes = []
    if has_start_guide:
        keyframes.append(
            {
                "resolved_frame_index": start_guide_frame_index,
                "latent": vae.encode(first),
            }
        )
    if endpoint is not None:
        last = _resize(endpoint, width, height, "center")
        token_images.append(last)
        keyframes.append(
            {
                "resolved_frame_index": endpoint_frame_index,
                "latent": vae.encode(last),
            }
        )
    tokens = clip.tokenize(selected_prompt, images=token_images)
    conditioning = clip.encode_from_tokens_scheduled(tokens)
    conditioning_values = {}
    if keyframes:
        conditioning_values["minimax_keyframes"] = keyframes
    if visual_condition_strength != _NATIVE_VISUAL_CONDITION_STRENGTH:
        conditioning_values["minimax_visual_cond_noise_aug"] = (
            visual_condition_strength
        )
    if conditioning_values:
        conditioning = node_helpers.conditioning_set_values(
            conditioning, conditioning_values
        )
    return io.NodeOutput(conditioning)
