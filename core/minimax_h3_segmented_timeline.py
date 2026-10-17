# MiniMax H3 Audio Timeline Planner [Eclipse Nova]
#
# Plans independent segmented renders from original images.

import json
import math
from typing import Any

from comfy_api.latest import io  # type: ignore

from .audio_timeline import (
    align_activity_gap,
    audio_duration_seconds,
    encoded_audio_activity,
)
from .image_helpers import flatten_images, unwrap_value
from .logger import log
from .minimax_h3_segment_plan import (
    CONDITIONING_FAMILIES,
    DEFAULT_TECHNICAL_CUT_INSTRUCTION,
    H3_FPS,
    MAX_RENDER_FRAMES,
    PLAN_KIND,
    PLAN_VERSION,
    REF_IMAGE_SIZES,
    RESET_ANCHORS,
    SEGMENT_STRATEGIES,
    TECHNICAL_SEAM_STYLES,
    TECHNICAL_SPLIT_SOURCES,
    audio_shape,
    build_analysis_manifest,
    build_segment_tasks,
    is_h3_frame_count,
    parse_manual_transition_times,
    single_image_gap_boundaries,
    space_transition_frames,
    task_uses_intentional_camera_cut,
    validate_segment_plan,
)

_LOG_PREFIX = "MiniMax H3 Audio Timeline Planner"


def _string_items(value: Any) -> list[str]:
    items: list[str] = []

    def collect(item: Any) -> None:
        if isinstance(item, (list, tuple)):
            for child in item:
                collect(child)
        elif isinstance(item, str) and item.strip():
            items.append(item.strip())

    collect(value)
    return items


def _number(
    value: Any,
    name: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{name} must be from {minimum} to {maximum}.")
    return float(value)


def plan_segments(
    audio,
    image_batch,
    conditioning_family,
    segment_strategy,
    warmup_seconds,
    reset_anchor,
    technical_split_source,
    ref_image_size,
    max_render_frames,
    align_to_activity_gap,
    transition_edge,
    search_window_seconds,
    min_gap_duration,
    resume_hold_duration,
    audio_encoder_output=None,
    conditioning_audio=None,
    manual_transition_times=None,
    technical_seam_style="plain_reset",
    technical_cut_instruction=DEFAULT_TECHNICAL_CUT_INSTRUCTION,
):
    audio = unwrap_value(audio)
    conditioning_family = unwrap_value(
        conditioning_family, "fl2va_keyframes"
    )
    segment_strategy = unwrap_value(segment_strategy, "warmup_reset")
    warmup_seconds = unwrap_value(warmup_seconds, 2.0)
    reset_anchor = unwrap_value(reset_anchor, "first_only")
    technical_split_source = unwrap_value(
        technical_split_source, "original_image_reset"
    )
    ref_image_size = unwrap_value(ref_image_size, "match")
    manual_transition_times = unwrap_value(manual_transition_times, "")
    max_render_frames = unwrap_value(max_render_frames, MAX_RENDER_FRAMES)
    align_to_activity_gap = unwrap_value(align_to_activity_gap, True)
    transition_edge = unwrap_value(transition_edge, "activity_resume")
    search_window_seconds = unwrap_value(search_window_seconds, 5.0)
    min_gap_duration = unwrap_value(min_gap_duration, 0.25)
    resume_hold_duration = unwrap_value(resume_hold_duration, 0.15)
    audio_encoder_output = unwrap_value(audio_encoder_output)
    conditioning_audio = unwrap_value(conditioning_audio)
    technical_seam_style = unwrap_value(
        technical_seam_style, "plain_reset"
    )
    technical_cut_instructions = _string_items(technical_cut_instruction)
    if not technical_cut_instructions:
        technical_cut_instructions = [DEFAULT_TECHNICAL_CUT_INSTRUCTION]

    if conditioning_family not in CONDITIONING_FAMILIES:
        raise ValueError(f"Unsupported conditioning_family: {conditioning_family}")
    if segment_strategy not in SEGMENT_STRATEGIES:
        raise ValueError(f"Unsupported segment_strategy: {segment_strategy}")
    if reset_anchor not in RESET_ANCHORS:
        raise ValueError(f"Unsupported reset_anchor: {reset_anchor}")
    if technical_split_source not in TECHNICAL_SPLIT_SOURCES:
        raise ValueError(
            f"Unsupported technical_split_source: {technical_split_source}"
        )
    if technical_seam_style not in TECHNICAL_SEAM_STYLES:
        raise ValueError(
            f"Unsupported technical_seam_style: {technical_seam_style}"
        )
    if (
        technical_seam_style == "intentional_camera_cut"
        and technical_split_source != "original_image_reset"
    ):
        raise ValueError(
            "intentional_camera_cut requires technical_split_source="
            "original_image_reset."
        )
    if ref_image_size not in REF_IMAGE_SIZES:
        raise ValueError(f"Unsupported ref_image_size: {ref_image_size}")
    if not isinstance(manual_transition_times, str):
        raise TypeError("manual_transition_times must be a string.")
    warmup_seconds = _number(
        warmup_seconds, "warmup_seconds", minimum=0.0, maximum=10.0
    )
    search_window_seconds = _number(
        search_window_seconds,
        "search_window_seconds",
        minimum=0.0,
        maximum=10.0,
    )
    min_gap_duration = _number(
        min_gap_duration, "min_gap_duration", minimum=0.02, maximum=5.0
    )
    resume_hold_duration = _number(
        resume_hold_duration,
        "resume_hold_duration",
        minimum=0.02,
        maximum=5.0,
    )
    if (
        not isinstance(max_render_frames, int)
        or isinstance(max_render_frames, bool)
        or not is_h3_frame_count(max_render_frames)
    ):
        raise ValueError(
            "max_render_frames must follow H3's 17k+5 grid from 124 to 362."
        )
    if not isinstance(align_to_activity_gap, bool):
        raise TypeError("align_to_activity_gap must be boolean.")
    if transition_edge not in ("activity_resume", "silence_start"):
        raise ValueError(f"Unsupported transition_edge: {transition_edge}")

    if conditioning_family == "ref2va_active_reference":
        if segment_strategy != "warmup_reset":
            raise ValueError(
                "Ref2VA supports warmup_reset only; hard cuts and first/last "
                "bridges require FL2VA weights."
            )
        if reset_anchor != "first_only":
            raise ValueError("Ref2VA does not support positional reset endpoints.")
        if technical_split_source != "original_image_reset":
            raise ValueError(
                "Ref2VA technical tasks must reset from the active reference; "
                "mixing minimax_refs with continuity keyframes is excluded."
            )

    images = flatten_images(image_batch)
    if not images:
        raise ValueError("image_batch must contain at least one image.")
    image_count = len(images)
    master_waveform, sample_rate = audio_shape(audio)
    duration = audio_duration_seconds(audio)
    guide_audio = audio if conditioning_audio is None else conditioning_audio
    guide_waveform, guide_rate = audio_shape(guide_audio)
    guide_duration = audio_duration_seconds(guide_audio)
    if abs(guide_duration - duration) > 1.0 / H3_FPS:
        raise ValueError(
            "conditioning_audio duration must match the master audio within "
            "one 24 FPS frame."
        )
    total_frames = math.ceil(duration * H3_FPS)
    if total_frames < 1:
        raise ValueError("Audio must contain at least one output video frame.")
    warmup_frames = round(warmup_seconds * H3_FPS)
    if warmup_frames >= max_render_frames:
        raise ValueError("warmup_seconds leaves no room in max_render_frames.")
    if (
        technical_seam_style == "intentional_camera_cut"
        and conditioning_family == "fl2va_keyframes"
        and warmup_frames < 1
    ):
        raise ValueError(
            "intentional_camera_cut requires a non-zero FL2VA warmup so the "
            "exact source guide remains hidden."
        )

    notes: list[str] = []
    manual_times: list[float] = []
    target_frames: list[int] = []
    transition_source = "single_image"
    if image_count > 1:
        manual = parse_manual_transition_times(
            manual_transition_times, image_count, total_frames
        )
        if manual is None:
            transition_source = "even_distribution"
            target_frames = [
                round(total_frames * index / image_count)
                for index in range(1, image_count)
            ]
        else:
            transition_source = "manual_seconds"
            manual_times, target_frames = manual
    elif manual_transition_times.strip():
        notes.append("Single image: manual transition times ignored.")

    candidates = list(target_frames)
    activity = None
    activity_error = "alignment disabled"
    if align_to_activity_gap:
        activity, activity_error = encoded_audio_activity(audio_encoder_output)
    if activity is not None and image_count > 1:
        for index, target in enumerate(target_frames):
            aligned, details = align_activity_gap(
                activity,
                target,
                H3_FPS,
                transition_edge,
                search_window_seconds,
                min_gap_duration,
                resume_hold_duration,
                minimum_frame=1,
                maximum_frame=total_frames - 1,
            )
            if aligned is None:
                notes.append(
                    f"Transition {index + 1}: frame {target} retained; {details}."
                )
            else:
                candidates[index] = aligned
                notes.append(
                    f"Transition {index + 1}: frame {target} -> {aligned} "
                    f"({transition_edge}); {details}."
                )
    elif align_to_activity_gap and image_count > 1:
        notes.append(f"Activity-alignment fallback: {activity_error}.")

    transition_frames, spacing_notes = space_transition_frames(
        candidates, total_frames
    )
    notes.extend(f"Spacing adjustment: {item}." for item in spacing_notes)
    continuation_frames: list[int] = []
    if image_count == 1 and activity is not None:
        hidden_tail = 1 if reset_anchor == "same_first_last_experimental" else 0
        visible_capacity = max_render_frames - warmup_frames - hidden_tail
        continuation_frames, continuation_notes = single_image_gap_boundaries(
            activity,
            total_frames,
            transition_edge,
            min_gap_duration,
            resume_hold_duration,
            max(1, visible_capacity),
        )
        notes.extend(continuation_notes)
    elif image_count == 1 and align_to_activity_gap:
        notes.append(f"Single-image activity fallback: {activity_error}.")

    tasks = build_segment_tasks(
        transition_frames=transition_frames,
        continuation_frames=continuation_frames,
        total_frames=total_frames,
        image_count=image_count,
        sample_count=master_waveform.shape[-1],
        sample_rate=sample_rate,
        conditioning_sample_count=guide_waveform.shape[-1],
        conditioning_sample_rate=guide_rate,
        conditioning_family=conditioning_family,
        segment_strategy=segment_strategy,
        warmup_frames=warmup_frames,
        reset_anchor=reset_anchor,
        technical_split_source=technical_split_source,
        technical_seam_style=technical_seam_style,
        ref_image_size=ref_image_size,
        max_render_frames=max_render_frames,
    )
    plan: dict[str, Any] = {
        "kind": PLAN_KIND,
        "version": PLAN_VERSION,
        "fps": H3_FPS,
        "sample_rate": sample_rate,
        "sample_count": master_waveform.shape[-1],
        "conditioning_sample_rate": guide_rate,
        "conditioning_sample_count": guide_waveform.shape[-1],
        "total_frames": total_frames,
        "image_count": image_count,
        "conditioning_family": conditioning_family,
        "segment_strategy": segment_strategy,
        "warmup_seconds": warmup_seconds,
        "warmup_frames": warmup_frames,
        "reset_anchor": reset_anchor,
        "technical_split_source": technical_split_source,
        "technical_seam_style": technical_seam_style,
        "technical_cut_instruction": technical_cut_instructions[0],
        "technical_cut_instructions": technical_cut_instructions,
        "ref_image_size": ref_image_size,
        "manual_transition_times": manual_times,
        "transition_source": transition_source,
        "transition_frames": transition_frames,
        "continuation_frames": continuation_frames,
        "max_render_frames": max_render_frames,
        "align_to_activity_gap": align_to_activity_gap,
        "transition_edge": transition_edge,
        "search_window_seconds": search_window_seconds,
        "min_gap_duration": min_gap_duration,
        "resume_hold_duration": resume_hold_duration,
        "tasks": tasks,
    }
    technical_cut_number = 0
    for task in tasks:
        if task_uses_intentional_camera_cut(plan, task):
            task["technical_cut_prompt_index"] = (
                technical_cut_number % len(technical_cut_instructions)
            )
            technical_cut_number += 1
        else:
            task["technical_cut_prompt_index"] = None
    validate_segment_plan(plan)
    manifest = build_analysis_manifest(plan)
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True)
    render_lengths = sorted({task["render_frames"] for task in tasks})
    report_lines = [
        f"Timeline: {total_frames} frames at 24 fps ({duration:.3f}s)",
        f"Original images: {image_count}; transitions: {transition_frames}",
        (
            f"Conditioning: {conditioning_family}; strategy: "
            f"{segment_strategy}; reset: {reset_anchor}"
        ),
        (
            f"Warmup: {warmup_frames} frames ({warmup_seconds:g}s); "
            f"technical splits: {technical_split_source}; seam style: "
            f"{technical_seam_style}"
        ),
        (
            f"Master: {master_waveform.shape[-1]} samples at {sample_rate} Hz; "
            f"guide: {guide_waveform.shape[-1]} samples at {guide_rate} Hz"
        ),
        f"Tasks: {len(tasks)}; legal render lengths: {render_lengths}",
        "Retained ranges: "
        + ", ".join(
            f"{task['task_index']}:[{task['output_start_frame']},"
            f"{task['output_end_frame']})/image {task['source_image_index']}"
            for task in tasks
        ),
        *notes,
    ]
    report = "\n".join(report_lines)
    log.debug(_LOG_PREFIX, report)
    return io.NodeOutput(
        plan,
        max(0, len(tasks) - 1),
        total_frames,
        int(tasks[0]["keep_frames"]),
        manifest_json,
        report,
    )
