# MiniMax H3 Audio Plan Step [Eclipse Nova]
#
# Resolves one strict segmented-plan task without accepting legacy H3 plans.

import torch  # type: ignore
from comfy_api.latest import io  # type: ignore

from .frame_timeline import FrameTimeline
from .image_helpers import flatten_images, unwrap_value
from .logger import log
from .minimax_h3_segment_plan import (
    CONTINUITY_FRAMES,
    audio_shape,
    validate_segment_plan,
)

_LOG_PREFIX = "MiniMax H3 Audio Plan Step"


def resolve_segment(
    plan,
    task_index,
    conditioning_audio,
    image_batch,
    previous_frames=None,
    timeline=None,
):
    plan_value, tasks = validate_segment_plan(unwrap_value(plan))
    task_index = unwrap_value(task_index, 0)
    if not isinstance(task_index, int) or isinstance(task_index, bool):
        raise TypeError("task_index must be an integer.")
    if not 0 <= task_index < len(tasks):
        raise ValueError(
            f"task_index {task_index} is outside the plan's {len(tasks)} tasks."
        )

    images = flatten_images(image_batch)
    if len(images) != plan_value["image_count"]:
        raise ValueError("image_batch count differs from the segmented plan.")
    waveform, sample_rate = audio_shape(conditioning_audio)
    if (
        sample_rate != plan_value["conditioning_sample_rate"]
        or waveform.shape[-1] != plan_value["conditioning_sample_count"]
    ):
        raise ValueError(
            "conditioning_audio sample rate/count differs from the segmented plan."
        )

    task = tasks[task_index]
    output_start = task["output_start_frame"]
    if timeline is not None:
        if previous_frames is not None:
            raise ValueError("Connect timeline or previous_frames, not both.")
        if not isinstance(timeline, FrameTimeline) or timeline.fps != plan_value["fps"]:
            raise ValueError("Timeline type/FPS differs from the segmented plan.")
        if len(timeline) != output_start:
            raise ValueError(f"Accumulated timeline drift: expected {output_start} frames, received {len(timeline)}.")
    elif task_index == 0:
        if previous_frames is not None:
            previous = flatten_images(previous_frames)
            if previous:
                raise ValueError("Task 0 must not receive previous_frames.")
    else:
        if not isinstance(previous_frames, torch.Tensor) or previous_frames.ndim != 4:
            raise ValueError(
                "Extension tasks require accumulated previous_frames as one "
                "4D IMAGE batch."
            )
        if previous_frames.shape[0] != output_start:
            raise ValueError(
                f"Accumulated timeline drift at task {task_index}: expected "
                f"{output_start} frames, received {previous_frames.shape[0]}."
            )

    has_continuity = task["has_continuity"]
    continuity_clip = None
    if has_continuity:
        if (len(timeline) if timeline is not None else previous_frames.shape[0]) < CONTINUITY_FRAMES:
            raise ValueError(
                "Generated continuation requires 22 accumulated frames."
            )
        continuity_clip = (timeline.tail(CONTINUITY_FRAMES) if timeline is not None
                           else previous_frames[-CONTINUITY_FRAMES:])

    source_image = images[task["source_image_index"]]
    has_last_image = task["has_last_image"]
    last_image = (
        images[task["last_image_index"]] if has_last_image else source_image
    )

    audio_start = task["audio_start_sample"]
    audio_end = task["audio_end_sample"]
    audio_slice = dict(conditioning_audio)
    sliced_waveform = waveform[..., audio_start:audio_end].clone()
    pad_start = task["audio_pad_start_samples"]
    pad_end = task["audio_pad_end_samples"]
    if pad_start or pad_end:
        sliced_waveform = torch.nn.functional.pad(
            sliced_waveform, (pad_start, pad_end)
        )
    audio_slice["waveform"] = sliced_waveform
    audio_slice["sample_rate"] = sample_rate

    start_index = task["start_guide_frame_index"]
    endpoint_index = task["endpoint_frame_index"]
    log.debug(
        _LOG_PREFIX,
        (
            f"Task {task_index}: {task['task_role']}; output "
            f"[{task['output_start_frame']},{task['output_end_frame']}), "
            f"render {task['render_frames']}, crop "
            f"{task['crop_start_frames']}, keep {task['keep_frames']}, "
            f"owner/prompt {task['source_image_index']}, family "
            f"{task['conditioning_family']}."
        ),
    )
    return io.NodeOutput(
        audio_slice,
        continuity_clip,
        has_continuity,
        source_image,
        task["has_start_guide"],
        start_index if start_index is not None else -1,
        last_image,
        has_last_image,
        endpoint_index if endpoint_index is not None else -1,
        task["render_frames"],
        task["crop_start_frames"],
        task["keep_frames"],
        task["prompt_index"],
        task["conditioning_family"],
        task["ref_image_size"],
    )
