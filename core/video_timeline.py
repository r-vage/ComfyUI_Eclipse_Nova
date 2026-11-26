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
from .minimax_h3_prompts import generation_prompt, timed_shot_prompt
from .minimax_h3_segment_plan import (
    H3_FPS,
    PLAN_KIND,
    PLAN_VERSION,
    aligned_h3_length,
    audio_shape,
    build_segment_tasks,
    history_length,
    is_h3_frame_count,
    validate_segment_plan,
)
from .scene_motion_text import AnalyzedMotionDirection
from .video_reference_range import DURATIONS, reference_lengths
from .video_scene_transitions import (
    motion_regions,
    resolve_transitions,
    transition_report,
)
from .wan_timeline import WAN_KIND, build_extension_tasks, wan_parts

TIMELINE_TYPE = "ECLIPSE_VIDEO_TIMELINE"
MODELS = ("Native H3", "H3 lip-sync", "WAN InfiniteTalk")
FRAME_PLAN_MODELS = {PLAN_KIND: MODELS[1], WAN_KIND: MODELS[2]}
GUIDES = ("First frame", "First and last", "Active reference")
PER_SOURCE = "Per source clip"
IN_ORDER = "In order at scene cuts"
CYCLE = "Cycle at scene cuts"
EQUAL_TIME = "Equal time at scene cuts"
IMAGE_ASSIGNMENTS = (PER_SOURCE, IN_ORDER, CYCLE, EQUAL_TIME)
SHOT_MODES = ("Separate at cuts", "Group timed shots")


@dataclass(frozen=True)
class Scene:
    source: int
    image: int | None
    start: int
    end: int
    prompt: str
    direction: str


@dataclass(frozen=True)
class ShotGroup:
    shots: tuple[Scene, ...]
    render_start: int


@dataclass(frozen=True)
class VideoTimeline:
    plan: H3ClipPlan | dict
    scenes: tuple[Scene, ...]
    images: list
    soundtrack: dict | None
    guide: dict | None
    report: str
    global_prompt: str
    shot_groups: tuple[ShotGroup, ...] = ()

    @property
    def description_scenes(self):
        if self.shot_groups:
            return tuple(shot for group in self.shot_groups for shot in group.shots)
        return self.scenes

    def generation_prompts(self, descriptions=None):
        shots = self.description_scenes
        directions = [s.direction for s in shots] if descriptions is None else descriptions
        if len(directions) != len(shots) or any(not isinstance(text, str) for text in directions):
            raise ValueError("Supply one description per timeline scene in display order.")
        supplied_audio = model_path(self.plan) == MODELS[1]
        # A text-only writer has no local scene evidence when only global direction was supplied.
        directions = ["" if self.global_prompt.strip() and s.image is None and not s.direction.strip() else text
                      for s, text in zip(shots, directions, strict=True)]
        if self.shot_groups:
            metadata = self.plan.source_metadata if isinstance(self.plan, H3ClipPlan) else self.plan.get("source_metadata", {})
            continuous = {row["frame"] for row in metadata.get("scene_transitions", ()) if row["continue"]}
            prompts = []
            offset = 0
            for group in self.shot_groups:
                texts = directions[offset:offset + len(group.shots)]
                if supplied_audio and descriptions is not None:
                    texts = [shot.direction if text == shot.direction else
                             AnalyzedMotionDirection(text, getattr(shot.direction, "camera", ()))
                             for shot, text in zip(group.shots, texts, strict=True)]
                prompts.append(timed_shot_prompt(
                    texts, [s.start - group.render_start for s in group.shots], self.global_prompt,
                    supplied_audio=supplied_audio, continuations=[s.start in continuous for s in group.shots]))
                offset += len(group.shots)
            return prompts
        return [generation_prompt(text, self.global_prompt, supplied_audio=supplied_audio) for text in directions]

    def reviewed(self, prompts):
        if len(prompts) != len(self.scenes) or any(not isinstance(p, str) for p in prompts):
            raise ValueError("Review exactly one prompt per displayed scene or shot group, in order.")
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


def _reference_prefix(spans, mode, seconds, cuts, prompts):
    """Keep the active cuts and their original directions when joining clip prefixes."""
    available = tuple(end - start for _, start, end in spans)
    lengths = tuple(reference_lengths(available, mode, seconds))
    if lengths == available and (not cuts or cuts[-1] < spans[-1][2]):
        return spans, cuts, prompts
    starts = [start for _, start, _ in spans]
    # Scene analysis exports seconds to nine decimals. A serialized cut on a
    # fractional playlist join or cutoff still denotes that exact boundary.
    endpoints = [*starts, *(start + length for start, length in zip(starts, lengths))]
    exact = {Fraction(f"{float(t):.9f}"): t for t in endpoints}
    cuts = [exact.get(t, t) for t in cuts]
    scene_starts = sorted(set(starts).union(cuts))
    if cuts and len(prompts) == len(cuts) + 1:
        prompt_starts = [Fraction(), *cuts]
    elif len(prompts) == len(spans):
        prompt_starts = starts
    else:
        prompt_starts = scene_starts
    if len(prompts) > len(scene_starts):
        if cuts or len(spans) > 1:
            raise ValueError("Supply one prompt per source clip or planned scene, with cut times for additional scenes.")
        # Untimed manual lines split the selected single clip evenly in _clock.
        return ((spans[0][0], Fraction(), lengths[0]),), cuts, prompts

    joined, kept_cuts, directions = [], [], []
    offset = Fraction()
    for (identity, start, _), length in zip(spans, lengths):
        joined.append((identity, offset, offset + length))
        for moment in scene_starts[bisect_left(scene_starts, start):bisect_left(scene_starts, start + length)]:
            if moment != start:
                kept_cuts.append(offset + moment - start)
            index = bisect_right(prompt_starts, moment) - 1
            directions.append(prompts[index] if index < len(prompts) else "")
        offset += length
    return joined, kept_cuts, directions


def _clock(mode, seconds, video, timing_audio, image_count, prompts, cut_times, global_prompt, fps, image_assignment):
    source = None
    original_spans = ()
    cuts = [Fraction(item.strip()) for item in cut_times.split(",")] if cut_times.strip() else []
    if cuts and (cuts != sorted(set(cuts)) or cuts[0] <= 0):
        raise ValueError("Cut times must be strictly increasing and inside the selected timeline.")
    if video is not None:
        from .video_stream import video_frame_source

        source = video_frame_source(video)
        spans = source_spans(video, source.timing.duration)
        original_spans = spans
        if mode in DURATIONS[2:]:
            # Fixed-FPS playlist joins have already moved to the next encoded
            # frame. Apply only the final endpoint when the loader kept these
            # prefixes, or rounding at each join would trim the same clips twice.
            encoded_from = getattr(video, "eclipse_reference_lengths", ())
            if seconds != -1 and encoded_from and tuple(reference_lengths(encoded_from, mode, seconds)) == encoded_from:
                mode, seconds = DURATIONS[3], sum(encoded_from)
            spans, cuts, prompts = _reference_prefix(spans, mode, seconds, cuts, prompts)
            mode = DURATIONS[0]
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
        if seconds == -1:
            raise ValueError("Connect a reference video to use −1 for its available duration.")
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
        source_start = original_spans[i][1] if original_spans else start
        owners.append({"id": identity, "start": a, "end": b, "source_start": str(source_start),
                       "source_end": str(source_start + end - start)})
        edges.add(a)
    cut_frames = []
    prompt_frames = None
    if cuts:
        limit = source_duration if source else total
        if cuts[-1] >= limit:
            raise ValueError("Cut times must be strictly increasing and inside the selected timeline.")
        if source:
            source_starts = [start for _, start, _ in spans]
            exact_joins = {Fraction(f"{float(t):.9f}"): t for t in source_starts}
            cuts = [exact_joins.get(t, t) for t in cuts]
            if len(prompts) == len(cuts) + 1:
                prompt_times = [Fraction(), *cuts]
            elif len(prompts) == len(spans):
                prompt_times = source_starts
            else:
                prompt_times = sorted(set(source_starts).union(cuts))

            def project(moment):
                return round(output_time(bisect_right(source_starts, moment) - 1, moment) * fps)

            # Keep prompt ownership on the source clock. Several source shots can
            # start on one output frame, or at the exclusive end of the render.
            prompt_frames = [project(t) for t in prompt_times]
            cut_frames = sorted({frame for frame in map(project, cuts) if 0 < frame < end_frame})
        else:
            cut_frames = [round(t * fps) for t in cuts]
            if len(set(cut_frames)) != len(cuts) or min(cut_frames) <= 0 or max(cut_frames) >= end_frame:
                raise ValueError("Each explicit scene needs at least one retained frame.")
        edges.update(cut_frames)
    elif len(prompts) > len(spans):
        if len(spans) != 1:
            raise ValueError("Supply cut times when there are more scene prompts than source clips.")
        edges.update(round(Fraction(i * end_frame, len(prompts))) for i in range(1, len(prompts)))
    if len(prompts) > (len(prompt_frames) if prompt_frames is not None else len(edges) - 1):
        raise ValueError("There are more scene prompts than planned scenes.")
    scenes = []
    starts = [row["start"] for row in owners]
    for i, (a, b) in enumerate(pairwise(sorted(edges))):
        owner = bisect_right(starts, a) - 1
        prompt_index = i
        if prompt_frames is not None:
            prompt_index = bisect_right(prompt_frames, a) - 1
        elif len(prompts) == len(cut_frames) + 1 and cut_frames:
            prompt_index = bisect_right(cut_frames, a)
        elif len(prompts) == len(owners):
            prompt_index = owner
        direction = prompts[prompt_index] if prompt_index < len(prompts) else ""
        text = "\n\n".join(p for p in (global_prompt, direction) if p.strip())
        scenes.append(Scene(owner, owner % image_count if image_count else None, a, b, text, direction))
    return tuple(scenes), owners, source is not None and (bool(cut_frames) or len(owners) > 1)


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


def _group_shots(shots, model, guidance, cap, opening, later, closing, keep_source_joins, boundaries, motion):
    """Pack whole shots. A shot longer than one render keeps its normal continuations."""
    segmented = model == MODELS[1]
    prefix = later if segmented and guidance == GUIDES[2] else opening
    first = 0
    groups = []
    for i, shot in enumerate(shots[1:], 1):
        start = shots[first]
        endpoint = segmented and guidance == GUIDES[1] and (i + 1 < len(shots) or closing is not None)
        visible_limit = min(15 * H3_FPS, cap - prefix - int(endpoint))
        row = boundaries.get(shot.start, {})
        if (row.get("previous_prompt") or boundaries.get(start.start, {}).get("previous_prompt")
                or (row.get("picture", "cut") != "cut" and row.get("seconds"))
                or shot.image != start.image or (keep_source_joins and shot.source != start.source)
                or shot.end - start.start > visible_limit):
            groups.append(ShotGroup(shots[first:i], start.start - prefix))
            first, prefix = i, motion.get(str(shot.start), {}).get("incoming") or later
    groups.append(ShotGroup(shots[first:], shots[first].start - prefix))
    return tuple(groups)


def shot_group_report(metadata):
    groups = metadata.get("shot_start_frames")
    if not isinstance(groups, list) or not groups or any(not isinstance(group, list) or not group for group in groups):
        return ""
    return f"{SHOT_MODES[1]} · Shots per prompt · " + ", ".join(str(len(group)) for group in groups)


def _fit_guide(audio, total, fps):
    if audio is None:
        raise ValueError("Lip-sync requires conditioning audio. In Conditioning track, choose a recording, isolated vocals or an unmuted reference video with audio.")
    wave, rate = audio_shape(audio)
    if wave.ndim != 3 or wave.shape[0] != 1 or wave.shape[1] not in (1, 2) or not wave.shape[-1]:
        raise ValueError("Connect a nonempty mono or stereo conditioning track.")
    count = max(1, round(Fraction(total * rate, fps)))
    wave = wave[..., :count]
    return {**audio, "waveform": F.pad(wave, (0, count - wave.shape[-1])) if wave.shape[-1] < count else wave}


def _native_parts(scenes, cap, opening, warmup, guidance, motion):
    parts = []
    for i, scene in enumerate(scenes):
        pos = scene.start
        region = motion.get(str(scene.start), {})
        while pos < scene.end:
            prefix = opening if not parts else warmup
            explicit = region.get("incoming", 0) if pos == scene.start else 0
            if pos > scene.start and (guidance != GUIDES[2] or region.get("technical")):
                prefix = history_length(pos - scene.start)
                if guidance == GUIDES[2]:
                    explicit = prefix
            if explicit:
                prefix = explicit
            keep = min(scene.end - pos, cap - prefix)
            parts.append(H3Clip(pos, keep, aligned_h3_length(prefix + keep), i, scene.prompt,
                                source_index=scene.source, crop_start=prefix, motion_frames=explicit))
            pos += keep
    return parts


def _segmented(scenes, guide, soundtrack, cap, opening, warmup, guidance, closing_image_index, motion):
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
    if motion:
        settings["motion_regions"] = {str(s.start): motion[str(s.start)] for s in scenes if str(s.start) in motion}
    tasks, _ = build_segment_tasks(**settings)
    return {"kind": PLAN_KIND, "version": PLAN_VERSION, "fps": 24, **settings, "tasks": tasks}


def _h3_layout(model, scenes, guide, sound, cap, opening, later, guidance, closing_image_index, skip_tail, motion=None):
    motion = motion or {}
    total = scenes[-1].end
    if model == MODELS[0]:
        parts = _native_parts(scenes, cap, opening, later, guidance, motion)
        if len(parts) > 1 and parts[-1].part == parts[-2].part and parts[-1].keep <= skip_tail:
            total = parts.pop().start
        return parts, total
    plan = _segmented(scenes, guide, sound, cap, opening, later, guidance, closing_image_index, motion)
    tasks = plan["tasks"]
    if tasks[-1]["is_technical_seam"] and tasks[-1]["keep_frames"] <= skip_tail:
        total = tasks[-1]["output_start_frame"]
        if closing_image_index is not None:
            trimmed = (*scenes[:-1], replace(scenes[-1], end=total))
            plan = _segmented(trimmed, guide, sound, cap, opening, later, guidance, closing_image_index, motion)
        else:
            tasks.pop()
            tasks[-1]["is_final"] = True
            plan["total_frames"] = total
    validate_segment_plan(plan)
    return plan, total


def _h3_scene_layout(shots, transitions, protected, group_shots, keep_source_joins, closing_index,
                     model, guide, sound, capacity, opening, later, guidance, skip_tail):
    boundaries = resolve_transitions(shots, transitions, h3=True, protect_source_edits=protected)
    continuous_splits = bool(transitions and transitions["rules"].get(0, ("Cut",))[0] == "Continue shot" and not protected)
    motion = motion_regions(shots, boundaries, guidance, continuous_splits,
                            paired_endpoints=model == MODELS[1] or closing_index is not None)
    groups, scenes, closing_slot = (), shots, None
    if group_shots:
        if closing_index is not None:
            closing_slot = shots[closing_index].image if closing_index < len(shots) else closing_index
        groups = _group_shots(shots, model, guidance, capacity, opening, later, closing_slot,
                              keep_source_joins, boundaries, motion)
        scenes = tuple(replace(group.shots[0], end=group.shots[-1].end) for group in groups)
        if closing_slot is not None:
            closing_index = next((i for i, s in enumerate(scenes) if s.image == closing_slot), len(scenes))
    plan, total = _h3_layout(model, scenes, guide, sound, capacity, opening, later, guidance, closing_index, skip_tail, motion)
    if boundaries:
        motion_by_start = ({c.start: c.motion_frames for c in plan} if model == MODELS[0] else
                           {t["output_start_frame"]: t["crop_start_frames"] if t["has_continuity"] else 0 for t in plan["tasks"]})
        for frame, row in boundaries.items():
            if row["continue"]:
                row["motion_frames"] = motion_by_start.get(frame)
    return plan, total, scenes, groups, boundaries, closing_index, closing_slot


def plan_timeline(model, duration_source, seconds, global_prompt="", scene_prompts=(), cut_times="",
                  images=None, reference_video=None, timing_audio=None, conditioning_audio=None, soundtrack=None,
                  guidance="First frame", h3_capacity=362, wan_context=81, wan_overlap=9,
                  opening_warmup=0., warmup=0., skip_tail_frames=0, image_assignment=PER_SOURCE,
                  shot_mode=SHOT_MODES[0], transitions=None):
    if model not in MODELS or guidance not in GUIDES:
        raise ValueError("Unknown video model or guidance mode.")
    if image_assignment not in IMAGE_ASSIGNMENTS:
        raise ValueError("Unknown timeline image assignment.")
    if shot_mode not in SHOT_MODES:
        raise ValueError("Choose a timeline shot mode.")
    fps = 25 if model == MODELS[2] else 24
    frames = flatten_images(images)
    if model != MODELS[0] and not frames:
        raise ValueError("Lip-sync generation requires a reference image.")
    if guidance == GUIDES[2] and model == MODELS[0] and not frames:
        raise ValueError("Active reference guidance requires a source image.")
    scenes, sources, source_edits = _clock(duration_source, seconds, reference_video, timing_audio, len(frames),
                                           scene_prompts, cut_times, global_prompt, fps, image_assignment)
    scene_count = len(scenes)
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
    shot_groups = ()
    closing_slot = None
    protected = model == MODELS[1] and source_edits
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
        shots = scenes = _assign_images(scenes, len(frames), image_assignment, total)
        boundaries = resolve_transitions(shots, transitions, h3=False, protect_source_edits=False)
    else:
        if not is_h3_frame_count(h3_capacity) or not 0 <= max(opening, later) < h3_capacity or min(opening, later) < 0:
            raise ValueError("Use an H3 render capacity from 124 to 362 on the 17k+5 grid with room for visible frames.")
        full_duration = total
        shots = _assign_images(scenes, len(frames), image_assignment, total)
        seen = set()
        while True:
            layout = _h3_scene_layout(shots, transitions, protected, shot_mode == SHOT_MODES[1], reference_video is not None,
                                      closing_image_index, model, guide, sound, h3_capacity, opening, later, guidance, skip_tail_frames)
            plan, total, render_scenes, shot_groups, boundaries, resolved_closing, closing_slot = layout
            if (total == full_duration and not seen) or not skip_tail_frames or image_assignment != EQUAL_TIME or len(frames) < 2:
                break
            reassigned = _assign_images(scenes, len(frames), image_assignment, total)
            if reassigned == shots:
                break
            seen.add(tuple(s.image for s in shots))
            if tuple(s.image for s in reassigned) in seen:
                # Conflicting tail/guide choices: retain the final part and its full-clock assignments.
                reassigned = _assign_images(scenes, len(frames), image_assignment, full_duration)
                skip_tail_frames = 0
            shots = reassigned
        scenes, closing_image_index = render_scenes, resolved_closing
        part_count = len(plan if model == MODELS[0] else plan["tasks"])
    sound = fit_soundtrack(sound, total, fps)
    starts = [s.image for s in scenes]
    metadata = {"sources": sources, "scene_sources": [s.source for s in scenes], "scene_images": starts,
                "image_assignment": image_assignment, "guidance": guidance, "duration_source": duration_source}
    if transitions and (protected or model == MODELS[2]) and any(
        shot == "Continue shot" or weight for shot, weight, _, _ in transitions["rules"].values()
    ):
        metadata["transition_note"] = ("H3 lip-sync follows the reference video's cuts and uses each incoming prompt at full strength."
                                       if protected else "WAN InfiniteTalk uses its own motion and prompt conditioning.")
    if boundaries:
        metadata["scene_transitions"] = [row for frame, row in boundaries.items() if frame < total]
        metadata["scene_boundaries"] = [s.start for s in shots[1:] if s.start < total]
    if shot_groups:
        metadata["shot_start_frames"] = [[s.start for s in group.shots] for group in shot_groups]
    # Frame-based renderers address references by scene. Native H3 uses the input slots directly.
    selected = frames if model == MODELS[0] else [frames[i] for i in starts]
    if closing_image_index is not None:
        closing = closing_slot if closing_slot is not None else (
            starts[closing_image_index] if closing_image_index < len(scenes) else closing_image_index)
        metadata["scene_end_images"] = [*starts[1:], closing]
        if model == MODELS[1] and closing_image_index == len(scenes):
            selected.append(frames[closing])
    omitted = scenes[-1].end - total
    report = (f"{model} · Source clips {len(sources)} · Scenes {scene_count} · Render parts {part_count}\n"
              f"{total} retained frames at {fps} FPS ({total / fps:.3f} s). Skipped final continuation: {omitted} frames.")
    if image_report := scene_image_report(metadata):
        report += "\n" + image_report
    if transitions_text := transition_report(metadata):
        report += "\n" + transitions_text
    if shot_groups:
        report += "\n" + shot_group_report(metadata)
    elif model == MODELS[2] and shot_mode == SHOT_MODES[1]:
        report += "\nWAN InfiniteTalk renders its own scene transitions. Timed shot grouping applies to H3."
    if model == MODELS[2] and guidance == GUIDES[1]:
        report += "\nWAN InfiniteTalk uses one reference image per scene."
    if model == MODELS[0]:
        clips = tuple(replace(c, image_index=starts[c.part]) for c in plan)
        plan = H3ClipPlan(clips, total, "selected soundtrack" if sound else "H3-generated audio",
                          sound, report, soundtrack_only=True, source_metadata=metadata)
    else:
        plan["source_metadata"] = metadata
    if model == MODELS[1] and sound is not None:
        plan["sample_count"] = sound["waveform"].shape[-1]
    timeline = VideoTimeline(plan, scenes, selected, sound, guide, report, global_prompt, shot_groups)
    return timeline.reviewed(timeline.generation_prompts() if shot_groups else [scene.prompt for scene in scenes])
