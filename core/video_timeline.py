"""Shared scene clock and reviewed inputs for the three video render pipelines."""
import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import pairwise

import torch.nn.functional as F

from .image_helpers import flatten_images
from .minimax_h3_clips import H3Clip, H3ClipPlan
from .minimax_h3_native_plan import fit_soundtrack, source_spans
from .minimax_h3_prompts import generation_prompt
from .minimax_h3_segment_plan import (
    CONTINUITY_FRAMES,
    PLAN_KIND,
    PLAN_VERSION,
    aligned_h3_length,
    audio_shape,
    build_segment_tasks,
    is_h3_frame_count,
    validate_segment_plan,
)
from .wan_timeline import WAN_KIND, build_extension_tasks, wan_parts

TIMELINE_TYPE = "ECLIPSE_VIDEO_TIMELINE"
MODELS = ("Native H3", "H3 lip-sync", "WAN InfiniteTalk")
FRAME_PLAN_MODELS = {PLAN_KIND: MODELS[1], WAN_KIND: MODELS[2]}
DURATIONS = ("Source clip lengths", "Audio track length", "Seconds per clip", "Total seconds")
GUIDES = ("First frame", "First and last", "Active reference")
PER_SOURCE = "Per source clip"
IN_ORDER = "In order at scene cuts"
CYCLE = "Cycle at scene cuts"
EQUAL_TIME = "Equal time at scene cuts"
IMAGE_ASSIGNMENTS = (PER_SOURCE, IN_ORDER, CYCLE, EQUAL_TIME)


@dataclass(frozen=True)
class Scene:
    source: int
    image: int | None
    start: int
    end: int
    prompt: str
    direction: str


@dataclass(frozen=True)
class VideoTimeline:
    plan: H3ClipPlan | dict
    scenes: tuple[Scene, ...]
    images: list
    soundtrack: dict | None
    guide: dict | None
    report: str
    global_prompt: str

    def generation_prompts(self, descriptions=None):
        directions = [s.direction for s in self.scenes] if descriptions is None else descriptions
        if len(directions) != len(self.scenes) or any(not isinstance(text, str) for text in directions):
            raise ValueError("Supply one description per timeline scene in display order.")
        supplied_audio = model_path(self.plan) == MODELS[1]
        assembled = []
        for scene, text in zip(self.scenes, directions, strict=True):
            # With only a global prompt, a text-only writer has no local scene
            # evidence. Use the user's performance directly in that case.
            if self.global_prompt.strip() and scene.image is None and not scene.direction.strip():
                text = ""
            assembled.append(generation_prompt(text, self.global_prompt, supplied_audio=supplied_audio))
        return assembled

    def reviewed(self, prompts):
        if len(prompts) != len(self.scenes) or any(not isinstance(p, str) for p in prompts):
            raise ValueError("Review exactly one prompt per scene in the displayed order.")
        prompts = list(prompts)
        if isinstance(self.plan, H3ClipPlan):
            plan = replace(self.plan, clips=tuple(replace(c, prompt=prompts[c.part]) for c in self.plan.clips),
                           source_metadata={**self.plan.source_metadata, "reviewed_prompts": prompts})
        else:
            plan = {**self.plan, "reviewed_prompts": prompts}
        return replace(self, plan=plan, scenes=tuple(replace(s, prompt=p) for s, p in zip(self.scenes, prompts)))


def model_path(plan):
    if isinstance(plan, str) and plan in MODELS:
        return plan
    if isinstance(plan, H3ClipPlan):
        return MODELS[0]
    if isinstance(plan, dict) and plan.get("kind") in FRAME_PLAN_MODELS:
        return FRAME_PLAN_MODELS[plan["kind"]]
    raise ValueError("Connect a resolved video timeline plan.")


def _clock(mode, seconds, video, timing_audio, image_count, prompts, cut_times, global_prompt, fps, image_assignment):
    source = None
    if video is not None:
        from .video_stream import video_frame_source

        source = video_frame_source(video)
        spans = source_spans(video, source.timing.duration)
    else:
        count = max(1, image_count)
        if count == 1 and mode == DURATIONS[2] and not cut_times.strip():
            count = max(count, len(prompts))
        spans = tuple((f"clip-{i + 1}", Fraction(i), Fraction(i + 1)) for i in range(count))
    if mode == DURATIONS[0]:
        if source is None:
            raise ValueError("Source clip lengths requires a reference video.")
        total = spans[-1][2]
    elif mode == DURATIONS[1]:
        if timing_audio is None:
            raise ValueError("Audio track length requires timing audio. Choose an available source in Duration track or select a different duration source.")
        wave, rate = audio_shape(timing_audio)
        total = Fraction(wave.shape[-1], rate)
    elif mode in DURATIONS[2:]:
        total = Fraction(str(seconds)) * (len(spans) if mode == DURATIONS[2] else 1)
    else:
        raise ValueError("Choose a duration source.")
    if not 0 < total <= 86400:
        raise ValueError("Choose a duration between zero and 24 hours, with at least one frame.")
    end_frame = math.ceil(total * fps)
    if source is None and image_assignment != PER_SOURCE and (cut_times.strip() or len(prompts) > len(spans)):
        # With no real source boundaries, the supplied shots define the scene clock.
        spans = (("clip-1", Fraction(0), Fraction(1)),)
    source_duration = spans[-1][2]
    def output_time(i, moment):
        start, end = spans[i][1:]
        if mode == DURATIONS[2]:
            return (i + (moment - start) / (end - start)) * total / len(spans)
        return moment * total / source_duration

    edges = {0, end_frame}
    owners = []
    for i, (identity, start, end) in enumerate(spans):
        a = round(output_time(i, start) * fps)
        b = end_frame if i + 1 == len(spans) else round(output_time(i, end) * fps)
        if a >= b:
            raise ValueError("Each source clip needs at least one retained frame.")
        owners.append({"id": identity, "start": a, "end": b, "source_start": str(start), "source_end": str(end)})
        edges.add(a)
    cut_frames = []
    if cut_times.strip():
        cuts = [Fraction(item.strip()) for item in cut_times.split(",")]
        limit = source_duration if source else total
        if cuts != sorted(set(cuts)) or cuts[0] <= 0 or cuts[-1] >= limit:
            raise ValueError("Cut times must be strictly increasing and inside the selected timeline.")
        if source:
            starts = [a for _, a, _ in spans]
            cuts = [output_time(bisect_right(starts, t) - 1, t) for t in cuts]
        cut_frames = [round(t * fps) for t in cuts]
        if len(set(cut_frames)) != len(cuts) or min(cut_frames) <= 0 or max(cut_frames) >= end_frame:
            raise ValueError("Each explicit scene needs at least one retained frame.")
        edges.update(cut_frames)
    elif len(prompts) > len(spans):
        if len(spans) != 1:
            raise ValueError("Supply cut times when there are more scene prompts than source clips.")
        edges.update(round(Fraction(i * end_frame, len(prompts))) for i in range(1, len(prompts)))
    if len(prompts) > len(edges) - 1:
        raise ValueError("There are more scene prompts than planned scenes.")
    scenes = []
    starts = [row["start"] for row in owners]
    for i, (a, b) in enumerate(pairwise(sorted(edges))):
        owner = bisect_right(starts, a) - 1
        prompt_index = i
        if len(prompts) == len(cut_frames) + 1 and cut_frames:
            prompt_index = bisect_right(cut_frames, a)
        elif len(prompts) == len(owners):
            prompt_index = owner
        direction = prompts[prompt_index] if prompt_index < len(prompts) else ""
        text = "\n\n".join(p for p in (global_prompt, direction) if p.strip())
        scenes.append(Scene(owner, owner % image_count if image_count else None, a, b, text, direction))
    return tuple(scenes), owners


def _assign_images(scenes, count, assignment, total):
    if count < 2 or assignment == PER_SOURCE:
        return scenes
    if assignment == EQUAL_TIME:
        # Reserve one whole scene for each remaining image. Ties use the earlier cut.
        groups = min(len(scenes), count)
        starts = [s.start for s in scenes]
        switches = []
        earliest = 1
        for i in range(1, groups):
            latest = len(scenes) - (groups - i)
            target = Fraction(i * total, groups)
            right = bisect_left(starts, target, earliest, latest)
            cut = min(range(max(earliest, right - 1), right + 1), key=lambda j: abs(starts[j] - target))
            switches.append(cut)
            earliest = cut + 1
        indices = (bisect_right(switches, i) for i in range(len(scenes)))
    elif assignment == CYCLE:
        indices = (i % count for i in range(len(scenes)))
    else:
        indices = (min(i, count - 1) for i in range(len(scenes)))
    return tuple(replace(scene, image=image) for scene, image in zip(scenes, indices, strict=True))


def scene_image_report(metadata):
    starts = metadata.get("scene_images")
    if not isinstance(starts, list) or not starts or any(type(i) is not int or i < 0 for i in starts):
        return ""
    ends = metadata.get("scene_end_images")
    if isinstance(ends, list) and len(ends) == len(starts) and all(type(i) is int and i >= 0 for i in ends):
        slots = [f"{a + 1}→{b + 1}" for a, b in zip(starts, ends)]
    else:
        slots = [str(i + 1) for i in starts]
    return f"Scene images ({metadata.get('image_assignment', PER_SOURCE)}) · " + ", ".join(slots)


def _fit_guide(audio, total, fps):
    if audio is None:
        raise ValueError("Lip-sync requires conditioning audio. In Conditioning track, choose a recording, isolated vocals or an unmuted reference video with audio.")
    wave, rate = audio_shape(audio)
    if wave.ndim != 3 or wave.shape[0] != 1 or wave.shape[1] not in (1, 2) or not wave.shape[-1]:
        raise ValueError("Connect a nonempty mono or stereo conditioning track.")
    count = max(1, round(Fraction(total * rate, fps)))
    wave = wave[..., :count]
    return {**audio, "waveform": F.pad(wave, (0, count - wave.shape[-1])) if wave.shape[-1] < count else wave}


def _native_parts(scenes, cap, opening, warmup, guidance):
    parts = []
    for i, scene in enumerate(scenes):
        pos = scene.start
        while pos < scene.end:
            prefix = opening if not parts else warmup
            if pos > scene.start and guidance != GUIDES[2]:
                available = pos - scene.start
                prefix = CONTINUITY_FRAMES if available >= CONTINUITY_FRAMES else 5 if available >= 5 else 1
            keep = min(scene.end - pos, cap - prefix)
            parts.append(H3Clip(pos, keep, aligned_h3_length(prefix + keep), i, scene.prompt,
                                source_index=scene.source, crop_start=prefix))
            pos += keep
    return parts


def _segmented(scenes, guide, soundtrack, cap, opening, warmup, guidance, closing_image_index):
    total = scenes[-1].end
    wave, rate = audio_shape(soundtrack if soundtrack is not None else guide)
    vocals, vocal_rate = audio_shape(guide)
    ref = guidance == GUIDES[2]
    settings = {
        "transition_frames": [s.start for s in scenes[1:]], "continuation_frames": [],
        "total_frames": total, "image_count": len(scenes), "sample_count": wave.shape[-1], "sample_rate": rate,
        "conditioning_sample_count": vocals.shape[-1], "conditioning_sample_rate": vocal_rate,
        "conditioning_family": "ref2va_active_reference" if ref else "fl2va_keyframes",
        "segment_strategy": "first_last_bridge" if guidance == GUIDES[1] else "warmup_reset",
        "warmup_frames": warmup, "opening_warmup_frames": opening, "reset_anchor": "first_only",
        "technical_split_source": "original_image_reset" if ref else "generated_continuation",
        "technical_seam_style": "plain_reset", "ref_image_size": "match", "max_render_frames": cap,
    }
    if closing_image_index is not None:
        settings["closing_image_index"] = closing_image_index
    tasks, _ = build_segment_tasks(**settings)
    return {"kind": PLAN_KIND, "version": PLAN_VERSION, "fps": 24, **settings, "tasks": tasks}


def plan_timeline(model, duration_source, seconds, global_prompt="", scene_prompts=(), cut_times="",
                  images=None, reference_video=None, timing_audio=None, conditioning_audio=None, soundtrack=None,
                  guidance="First frame", h3_capacity=362, wan_context=81, wan_overlap=9,
                  opening_warmup=0., warmup=0., skip_tail_frames=0, image_assignment=PER_SOURCE):
    if model not in MODELS or guidance not in GUIDES:
        raise ValueError("Unknown video model or guidance mode.")
    if image_assignment not in IMAGE_ASSIGNMENTS:
        raise ValueError("Unknown timeline image assignment.")
    fps = 25 if model == MODELS[2] else 24
    frames = flatten_images(images)
    if model != MODELS[0] and not frames:
        raise ValueError("Lip-sync generation requires a reference image.")
    if guidance == GUIDES[2] and model == MODELS[0] and not frames:
        raise ValueError("Active reference guidance requires a source image.")
    scenes, sources = _clock(duration_source, seconds, reference_video, timing_audio, len(frames),
                             scene_prompts, cut_times, global_prompt, fps, image_assignment)
    total = scenes[-1].end
    guide = _fit_guide(conditioning_audio, total, fps) if model != MODELS[0] else None
    sound = fit_soundtrack(soundtrack, total, fps)
    opening, later = round(opening_warmup * fps), round(warmup * fps)
    closing_image_index = None
    if frames and model != MODELS[2] and guidance == GUIDES[1] and image_assignment != PER_SOURCE:
        # A bridge uses the following scene's reference. Give the final shot its own destination.
        if image_assignment == CYCLE:
            closing_image_index = len(scenes) % len(frames)
        elif image_assignment == IN_ORDER:
            closing_image_index = min(len(scenes), len(frames) - 1)
        else:
            closing_image_index = len(scenes) - 1
    if model == MODELS[2]:
        if wan_context < 5 or wan_context % 4 != 1 or not 1 <= wan_overlap <= min(33, wan_context - 1):
            raise ValueError("WAN requires 4k+1 context frames and 1–33 overlap frames below context length.")
        cuts = [s.start for s in scenes[1:]]
        base = min(wan_context, scenes[0].end)
        if base < total and base < wan_overlap:
            raise ValueError("The opening scene is shorter than the selected WAN motion overlap.")
        tasks = build_extension_tasks(base, total, cuts, wan_context, wan_overlap, later)
        if tasks and not tasks[-1]["starts_transition"] and tasks[-1]["keep_frames"] <= skip_tail_frames:
            total = tasks.pop()["start_frame"]
        plan = {
            "kind": WAN_KIND, "version": 1, "fps": fps,
            "mode": "single_reference" if len(scenes) == 1 else "multi_reference",
            "image_count": len(scenes), "context_length": wan_context, "overlap_frames": wan_overlap,
            "total_frames": total, "transition_frames": cuts, "base_keep_frames": base,
            "tasks": tasks,
        }
        part_count = len(wan_parts(plan))
    else:
        if not is_h3_frame_count(h3_capacity) or not 0 <= max(opening, later) < h3_capacity or min(opening, later) < 0:
            raise ValueError("Use an H3 render capacity from 124 to 362 on the 17k+5 grid with room for visible frames.")
        if model == MODELS[0]:
            parts = _native_parts(scenes, h3_capacity, opening, later, guidance)
            if len(parts) > 1 and parts[-1].part == parts[-2].part and parts[-1].keep <= skip_tail_frames:
                total = parts.pop().start
            part_count = len(parts)
        else:
            plan = _segmented(scenes, guide, sound, h3_capacity, opening, later, guidance, closing_image_index)
            tasks = plan["tasks"]
            if tasks[-1]["is_technical_seam"] and tasks[-1]["keep_frames"] <= skip_tail_frames:
                total = tasks[-1]["output_start_frame"]
                if closing_image_index is not None:
                    trimmed = (*scenes[:-1], replace(scenes[-1], end=total))
                    plan = _segmented(trimmed, guide, sound, h3_capacity, opening, later, guidance, closing_image_index)
                else:
                    tasks.pop()
                    tasks[-1]["is_final"] = True
                    plan["total_frames"] = total
            validate_segment_plan(plan)
            part_count = len(plan["tasks"])
    sound = fit_soundtrack(sound, total, fps)
    scenes = _assign_images(scenes, len(frames), image_assignment, total)
    starts = [s.image for s in scenes]
    metadata = {"sources": sources, "scene_sources": [s.source for s in scenes], "scene_images": starts,
                "image_assignment": image_assignment, "guidance": guidance, "duration_source": duration_source}
    # Frame-based renderers address references by scene. Native H3 uses the input slots directly.
    selected = frames if model == MODELS[0] else [frames[i] for i in starts]
    if closing_image_index is not None:
        closing = starts[closing_image_index] if closing_image_index < len(scenes) else closing_image_index
        metadata["scene_end_images"] = [*starts[1:], closing]
        if model == MODELS[1] and closing_image_index == len(scenes):
            selected.append(frames[closing])
    omitted = scenes[-1].end - total
    report = (f"{model} · {len(sources)} source clips · {len(scenes)} scenes · {part_count} render parts\n"
              f"{total} retained frames at {fps} FPS ({total / fps:.3f} s). Skipped final continuation: {omitted} frames.")
    if image_report := scene_image_report(metadata):
        report += "\n" + image_report
    if model == MODELS[2] and guidance == GUIDES[1]:
        report += "\nWAN InfiniteTalk uses one reference image per scene."
    if model == MODELS[0]:
        clips = tuple(replace(c, image_index=starts[c.part]) for c in parts)
        plan = H3ClipPlan(clips, total, "selected soundtrack" if sound else "H3-generated audio",
                          sound, report, soundtrack_only=True, source_metadata=metadata)
    else:
        plan["source_metadata"] = metadata
    if model == MODELS[1] and sound is not None:
        plan["sample_count"] = sound["waveform"].shape[-1]
    timeline = VideoTimeline(plan, scenes, selected, sound, guide, report, global_prompt)
    return timeline.reviewed([scene.prompt for scene in scenes])
