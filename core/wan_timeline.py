"""Frame-exact InfiniteTalk extension timing and bounded motion history."""
from typing import Any

import torch
import torch.nn.functional as F

from .frame_timeline import FrameTimeline
from .image_helpers import cat_and_fit_images, flatten_images, unwrap_value
from .logger import log

WAN_KIND = "WAN_LIPSYNC_PLAN"
_LOG_PREFIX = "WAN LipSync Plan Step"


def wan_parts(plan):
    """Expose the opening and extensions in absolute render order."""
    plan, extensions = validate_wan_plan(plan)
    base = {"start_frame": 0, "end_frame": plan["base_keep_frames"], "image_index": 0,
            "keep_frames": plan["base_keep_frames"], **plan.get("base_prompt", {})}
    return [base, *extensions]


def resolve_wan_part(plan, index, images, previous, blend_mode="linear"):
    parts = wan_parts(plan)
    if type(index) is not int or not 0 <= index < len(parts):
        raise ValueError("WAN part index is outside the saved plan.")
    if index:
        return resolve_extension(plan, index - 1, images, previous, blend_mode)
    frames = flatten_images(images)
    if previous is not None or len(frames) != plan["image_count"]:
        raise ValueError("The WAN opening requires the planned references and an empty timeline.")
    return frames[0], None, parts[0]["keep_frames"], 0, 0


def build_extension_tasks(
    base_keep_frames: int,
    total_frames: int,
    transition_frames: list[int],
    context_length: int,
    overlap_frames: int,
    warmup_frames: int = 0,
) -> list[dict[str, int | bool]]:
    stride = context_length - overlap_frames
    transition_set = set(transition_frames)
    tasks: list[dict[str, int | bool]] = []
    start_frame = base_keep_frames

    while start_frame < total_frames:
        image_index = sum(
            1 for transition_frame in transition_frames if transition_frame <= start_frame
        )
        next_transition = (
            transition_frames[image_index]
            if image_index < len(transition_frames)
            else total_frames
        )
        # Hidden generated lead-in uses preceding real audio; the visible range
        # remains at start_frame. Keep the fixed render length and budget less
        # visible content only on an image change.
        warmup = min(warmup_frames, start_frame - overlap_frames, stride - 1) if start_frame in transition_set else 0
        end_frame = min(start_frame + stride - warmup, next_transition, total_frames)
        if end_frame <= start_frame:
            raise ValueError("Timeline planning produced an empty extension task.")
        tasks.append(
            {
                "start_frame": start_frame,
                "end_frame": end_frame,
                "image_index": image_index,
                "keep_frames": end_frame - start_frame,
                "starts_transition": start_frame in transition_set,
                "warmup_frames": warmup,
            }
        )
        start_frame = end_frame

    return tasks


def _pyramid_blend(
    source: torch.Tensor,
    target: torch.Tensor,
    alpha: torch.Tensor,
    levels: int = 4,
) -> torch.Tensor:
    source_nchw = source.float().permute(0, 3, 1, 2)
    target_nchw = target.float().permute(0, 3, 1, 2)

    def laplacian(tensor: torch.Tensor) -> list[torch.Tensor]:
        gaussian = [tensor]
        for _ in range(levels - 1):
            if min(gaussian[-1].shape[-2:]) < 2:
                break
            gaussian.append(F.avg_pool2d(gaussian[-1], kernel_size=2, stride=2))

        bands: list[torch.Tensor] = []
        for index in range(len(gaussian) - 1):
            upsampled = F.interpolate(
                gaussian[index + 1],
                size=gaussian[index].shape[2:],
                mode="bilinear",
                align_corners=False,
            )
            bands.append(gaussian[index] - upsampled)
        bands.append(gaussian[-1])
        return bands

    source_bands = laplacian(source_nchw)
    target_bands = laplacian(target_nchw)
    blended_bands = [
        (1.0 - alpha) * source_band + alpha * target_band
        for source_band, target_band in zip(source_bands, target_bands)
    ]

    result = blended_bands[-1]
    for band in reversed(blended_bands[:-1]):
        result = (
            F.interpolate(
                result,
                size=band.shape[2:],
                mode="bilinear",
                align_corners=False,
            )
            + band
        )
    return result.permute(0, 2, 3, 1).to(source.dtype)


def _require_int(mapping: dict[str, Any], key: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Plan field '{key}' must be an integer.")
    return value


def validate_wan_plan(plan: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(plan, dict):
        raise ValueError("plan must be a WAN_LIPSYNC_PLAN dictionary.")
    if plan.get("kind") != WAN_KIND or plan.get("version") != 1:
        raise ValueError("Unsupported or invalid WAN_LIPSYNC_PLAN metadata.")

    mode = plan.get("mode")
    if mode not in ("single_reference", "multi_reference"):
        raise ValueError("Plan mode is invalid.")

    image_count = _require_int(plan, "image_count")
    total_frames = _require_int(plan, "total_frames")
    base_keep_frames = _require_int(plan, "base_keep_frames")
    context_length = _require_int(plan, "context_length")
    overlap_frames = _require_int(plan, "overlap_frames")
    if image_count < 1 or total_frames < 1:
        raise ValueError("Plan image_count and total_frames must be positive.")
    if not 0 < base_keep_frames <= total_frames:
        raise ValueError("Plan base_keep_frames is outside the timeline.")
    if overlap_frames < 1 or overlap_frames >= context_length:
        raise ValueError("Plan overlap_frames is incompatible with context_length.")

    tasks = plan.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("Plan tasks must be a list.")
    if len(tasks) == 0 and base_keep_frames != total_frames:
        raise ValueError("Plan has no tasks but does not cover the full timeline.")

    expected_start = base_keep_frames
    for task_index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise ValueError(f"Plan task {task_index} is not a dictionary.")
        start_frame = _require_int(task, "start_frame")
        end_frame = _require_int(task, "end_frame")
        image_index = _require_int(task, "image_index")
        keep_frames = _require_int(task, "keep_frames")
        starts_transition = task.get("starts_transition")
        if not isinstance(starts_transition, bool):
            raise ValueError(
                f"Plan task {task_index} field 'starts_transition' must be boolean."
            )
        if start_frame != expected_start:
            raise ValueError(f"Plan task {task_index} is not timeline-contiguous.")
        if end_frame <= start_frame or keep_frames != end_frame - start_frame:
            raise ValueError(f"Plan task {task_index} has an invalid frame range.")
        warmup = task.get("warmup_frames", 0)
        if type(warmup) is not int or warmup < 0 or warmup > start_frame - overlap_frames:
            raise ValueError(f"Plan task {task_index} has an invalid warmup.")
        if warmup and not starts_transition:
            raise ValueError("Warmup is only supported at image changes.")
        if keep_frames + warmup > context_length - overlap_frames:
            raise ValueError(f"Plan task {task_index} exceeds the retained stride.")
        if image_index < 0 or image_index >= image_count:
            raise ValueError(f"Plan task {task_index} has an invalid image index.")
        expected_start = end_frame

    if expected_start != total_frames:
        raise ValueError("Plan tasks do not end at total_frames.")
    return plan, tasks


def resolve_extension(plan, loop_index, image_batch, previous_frames, blend_mode):
    plan_value, tasks = validate_wan_plan(unwrap_value(plan))
    loop_index_value = unwrap_value(loop_index, 0)
    blend_mode_value = unwrap_value(blend_mode, "linear")
    if not isinstance(loop_index_value, int) or isinstance(loop_index_value, bool):
        raise ValueError("loop_index must be an integer.")
    if loop_index_value < 0 or loop_index_value >= len(tasks):
        raise ValueError(
            f"loop_index {loop_index_value} is outside the plan's "
            f"{len(tasks)} extension tasks."
        )
    if blend_mode_value not in ("linear", "pyramid"):
        raise ValueError(f"Unsupported blend_mode: {blend_mode_value}")
    disk = isinstance(previous_frames, FrameTimeline)
    if disk and plan_value["fps"] != 25:
        raise ValueError("InfiniteTalk disk timelines require 25 FPS to match its audio feature clock.")
    if disk and previous_frames.fps != plan_value["fps"]:
        raise ValueError("Timeline FPS differs from the Wan plan.")
    if not disk and (not isinstance(previous_frames, torch.Tensor) or previous_frames.ndim != 4):
        raise ValueError("previous_frames must be one 4D IMAGE batch.")

    images = flatten_images(image_batch)
    image_count = _require_int(plan_value, "image_count")
    if len(images) != image_count:
        raise ValueError(
            f"image_batch contains {len(images)} images but the plan expects "
            f"{image_count}."
        )

    task = tasks[loop_index_value]
    start_frame = _require_int(task, "start_frame")
    if previous_frames.shape[0] != start_frame:
        raise ValueError(
            f"Accumulated timeline drift at task {loop_index_value}: expected "
            f"{start_frame} frames, received {previous_frames.shape[0]}."
        )

    image_index = _require_int(task, "image_index")
    keep_frames = _require_int(task, "keep_frames")
    start_image = images[image_index]
    mode = plan_value["mode"]
    starts_transition = task["starts_transition"]
    overlap_frames = _require_int(plan_value, "overlap_frames")
    warmup = task.get("warmup_frames", 0)
    trim_image = overlap_frames + warmup
    audio_start = start_frame - trim_image
    if disk:
        previous_frames = previous_frames.tail(overlap_frames)

    if mode == "single_reference":
        if image_count != 1 or image_index != 0 or starts_transition:
            raise ValueError("Single-reference plan task metadata is inconsistent.")
        return start_image, previous_frames, keep_frames, trim_image, audio_start

    if not starts_transition:
        return start_image, previous_frames, keep_frames, trim_image, audio_start

    overlap_frames = _require_int(plan_value, "overlap_frames")
    if previous_frames.shape[0] < overlap_frames:
        raise ValueError(
            "A transition task does not have enough accumulated frames for "
            "the configured overlap."
        )
    if previous_frames.shape[-1] != start_image.shape[-1]:
        raise ValueError(
            "Reference and accumulated images have different channel counts."
        )

    target_image = start_image
    if (
        target_image.device != previous_frames.device
        or target_image.dtype != previous_frames.dtype
    ):
        target_image = target_image.to(
            device=previous_frames.device, dtype=previous_frames.dtype
        )
    fitted = cat_and_fit_images(
        [previous_frames[-1:], target_image], log_prefix=_LOG_PREFIX
    )
    if fitted is None or fitted.shape[0] != 2:
        raise ValueError("Unable to fit the transition reference to the timeline.")
    target_overlap = fitted[1:2].repeat(overlap_frames, 1, 1, 1)
    if warmup:
        # InfiniteTalk derives audio_start from this temporary batch length.
        # Shortening by W and cropping overlap+W preserves the original
        # visible frame/audio time. Reset the guide to the destination image;
        # the discarded generated frames settle its singing before the cut.
        conditioning_frames = previous_frames.clone() if disk else previous_frames[:start_frame - warmup].clone()
        conditioning_frames[-overlap_frames:] = target_overlap
        return start_image, conditioning_frames, keep_frames, trim_image, audio_start
    source_overlap = previous_frames[-overlap_frames:]
    alpha = torch.linspace(
        0.0,
        1.0,
        overlap_frames + 2,
        device=source_overlap.device,
        dtype=source_overlap.dtype,
    )[1:-1].view(-1, 1, 1, 1)

    if blend_mode_value == "pyramid":
        blended_overlap = _pyramid_blend(
            source_overlap, target_overlap, alpha
        )
    else:
        blended_overlap = (
            (1.0 - alpha) * source_overlap + alpha * target_overlap
        )

    conditioning_frames = previous_frames.clone()
    conditioning_frames[-overlap_frames:] = blended_overlap
    if conditioning_frames.shape[0] != (overlap_frames if disk else start_frame):
        raise ValueError("Transition conditioning changed the accumulated length.")

    log.debug(
        _LOG_PREFIX,
        f"Task {loop_index_value}: blended {overlap_frames} conditioning "
        f"frames toward image {image_index} via {blend_mode_value}.",
    )
    return start_image, conditioning_frames, keep_frames, trim_image, audio_start
