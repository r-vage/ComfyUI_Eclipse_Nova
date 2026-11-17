"""Source-clip image assignment and video-led timing for native H3 generation."""
import math
from bisect import bisect_left, bisect_right
from dataclasses import replace
from fractions import Fraction
from itertools import pairwise

from .image_helpers import flatten_images
from .minimax_h3_clips import FPS, H3Clip, H3ClipPlan, _plan_report, _text
from .minimax_h3_segment_plan import (
    aligned_h3_length,
    audio_shape,
    is_h3_frame_count,
    parse_manual_transition_times,
)


def source_spans(video, duration):
    """Read structured loader provenance; other VIDEO inputs are one clip."""
    rows = getattr(video, "eclipse_source_clips", None)
    if not rows:
        return (("video", Fraction(), duration),)
    spans = tuple((str(row["id"]), Fraction(row["start"]), Fraction(row["end"])) for row in rows)
    previous = Fraction()
    for _, start, end in spans:
        if start != previous or end <= start:
            raise ValueError("Source clip timing must be contiguous and positive.")
        previous = end
    # Encoders may round the tail to the output frame grid.
    if abs(previous - duration) > Fraction(1, 2):
        raise ValueError("Source clip timing does not match the loaded video.")
    return spans


def fit_soundtrack(audio, total_frames):
    if audio is None:
        return None
    waveform, rate = audio_shape(audio)
    if (waveform.ndim != 3 or waveform.shape[0] != 1 or waveform.shape[1] not in (1, 2)
            or waveform.shape[-1] == 0):
        raise ValueError("Selected audio excerpt must contain nonempty mono or stereo audio.")
    count = round(Fraction(total_frames, FPS) * rate)
    repeats = math.ceil(count / waveform.shape[-1])
    fitted = waveform.repeat(1, 1, repeats) if repeats > 1 else waveform
    return {**audio, "waveform": fitted[..., :count]}


def native_scene_prompts(plan):
    """Expose resolved text once per scene, keeping identical neighboring prompts."""
    if not isinstance(plan, H3ClipPlan) or not plan.soundtrack_only:
        raise ValueError("Connect a native Clip Planner_v2 plan.")
    prompts = {}
    for clip in plan.clips:
        if clip.part in prompts and prompts[clip.part] != clip.prompt:
            raise ValueError("Technical splits of a scene must share the same prompt for scene review.")
        prompts[clip.part] = clip.prompt
    return list(prompts.values())


def apply_native_scene_prompts(plan, prompts):
    originals = native_scene_prompts(plan)
    if not isinstance(prompts, list) or len(prompts) != len(originals) or any(not isinstance(p, str) for p in prompts):
        raise ValueError("Reviewed prompts must contain exactly one text per planned scene, in order.")
    by_scene = dict(zip(dict.fromkeys(clip.part for clip in plan.clips), prompts))
    return replace(plan, clips=tuple(replace(clip, prompt=by_scene[clip.part]) for clip in plan.clips))


def native_description_inputs(plan, images=None):
    """Pair each logical scene's complete instructions with its assigned image."""
    prompts = native_scene_prompts(plan)
    frames = flatten_images(images)
    if not frames:
        if any(clip.image_index is not None for clip in plan.clips):
            raise ValueError("Connect the same images used by H3 Prompt Plan_v2.")
        return [], [text if text.strip() else "Write one video clip description according to the selected task."
                    for text in prompts]
    scenes = dict.fromkeys(clip.part for clip in plan.clips)
    assigned = {}
    for clip in plan.clips:
        if clip.image_index is None or not 0 <= clip.image_index < len(frames):
            raise ValueError("Connect the same images used by H3 Prompt Plan_v2.")
        assigned.setdefault(clip.part, frames[clip.image_index])
    return ([assigned[part] for part in scenes],
            [text if text.strip() else "Describe this image for one video clip according to the selected task."
             for text in prompts])


def _prompt_spans(duration, image_count, parts, times):
    # Multiple images keep one clip each. A single image (or text only) can
    # supply several clips from the first/next prompt list.
    count = image_count if image_count > 1 else len(parts)
    if len(parts) > count:
        raise ValueError(f"{len(parts)} scene prompts were supplied for {count} images. Use one prompt per image.")
    total = Fraction(str(duration)) * count
    parsed = parse_manual_transition_times(times, 1, 2**63 - 1) if times.strip() else None
    if parsed:
        cuts = [Fraction(frame, FPS) for frame in parsed[1]]
        if len(cuts) != count - 1:
            raise ValueError(f"{count} clips require {count - 1} cut times, or leave cut times blank.")
        if cuts[-1] >= total:
            raise ValueError("Cut times must be inside the total video duration (clip count × duration per clip).")
        edges = [Fraction(), *cuts, total]
    else:
        edges = [Fraction(str(duration)) * i for i in range(count + 1)]
    return tuple((f"clip-{i + 1}", start, end) for i, (start, end) in enumerate(pairwise(edges)))


def plan_native_clips(duration, max_clip_frames=362, cut_times="", prompt="", first_prompt="",
                      next_prompts=None, images=None, image_prompts=None, audio=None, reference_video=None,
                      *, prompt_timing=False):
    if not math.isfinite(duration) or not 0 <= duration <= 86400:
        raise ValueError("Duration must be finite and between 0 and 86400 seconds.")
    if not is_h3_frame_count(max_clip_frames):
        raise ValueError("Max clip frames must be on H3's 17k+5 grid, from 124 to 362.")
    frames = flatten_images(images)
    descriptions = list(image_prompts or [])
    if descriptions and len(descriptions) != len(frames):
        raise ValueError("Image description count must match the enabled images. Describe each image individually.")
    if any(not isinstance(text, str) for text in descriptions):
        raise ValueError("Image descriptions must be text.")
    parts = [_text(first_prompt), *[_text(text) for text in (next_prompts or [])]]
    if prompt_timing:
        parts = [parts[0], *[text for text in parts[1:] if text.strip()]]
    times = _text(cut_times).strip()
    source = "loaded audio" if audio is not None else "H3-generated audio"
    if reference_video is not None:
        from .video_stream import video_frame_source

        reference = video_frame_source(reference_video)
        spans = source_spans(reference_video, reference.timing.duration)
        if audio is None and reference.has_audio and getattr(reference_video, "eclipse_source_has_audio", True):
            audio = reference.audio()
            if audio is not None:
                source = "reference video audio"
    else:
        if duration == 0:
            raise ValueError("Set a positive duration per image or text-only clip when no video is loaded.")
        if prompt_timing:
            spans = _prompt_spans(duration, len(frames), parts, times)
        else:
            seconds = Fraction(str(duration))
            spans = tuple((f"image-{i + 1}" if frames else "text", i * seconds, (i + 1) * seconds)
                          for i in range(max(1, len(frames))))
    parsed = parse_manual_transition_times(times, 1, 2**63 - 1) if times else None
    cuts = [Fraction(frame, FPS) for frame in parsed[1]] if parsed else []
    if prompt_timing and reference_video is not None:
        if cuts and cuts[-1] >= spans[-1][2]:
            raise ValueError("Cut times must be inside the loaded video timeline.")
        if not cuts and len(parts) > len(spans):
            cuts = [spans[-1][2] * i / len(parts) for i in range(1, len(parts))]
    # Scene timestamps are exported on H3's 24 FPS grid. Snap a rounded
    # playlist cut back to its exact source boundary before scaling.
    source_edges = [span[1] for span in spans[1:]]
    cuts = sorted({next((edge for edge in source_edges if abs(edge - cut) <= Fraction(1, 2 * FPS)), cut)
                   for cut in cuts})
    clips, metadata, output_start, scene_index = [], [], 0, 0
    used_prompts = set()
    for source_index, (identity, start, end) in enumerate(spans):
        length = Fraction(str(duration)) if duration > 0 else end - start
        # Round cumulative endpoints so a playlist does not accumulate frame drift.
        output_end = (math.ceil((source_index + 1) * length * FPS)
                      if duration > 0 and (reference_video is not None or not prompt_timing)
                      else math.ceil(end * FPS))
        count = output_end - output_start
        boundaries = [start, *[cut for cut in cuts if start < cut < end], end]
        targets = [output_start + round((cut - start) / (end - start) * count) for cut in boundaries]
        if any(b <= a for a, b in pairwise(targets)):
            raise ValueError("Duration is too short to retain every scene. Increase duration or reduce scene cuts.")
        image_index = source_index % len(frames) if frames else None
        metadata.append({"id": identity, "source_start": str(start), "source_end": str(end),
                         "output_start": output_start, "output_end": output_end, "image_index": image_index})
        for (scene_start, _), (a, b) in zip(pairwise(boundaries), pairwise(targets)):
            # Mandatory source boundaries must not consume another prompt when
            # the detector/manual source supplied one scene spanning that cut.
            prompt_index = bisect_right(cuts, scene_start)
            if not cuts:
                prompt_index = source_index if prompt_timing else min(source_index, len(parts) - 1)
            used_prompts.add(prompt_index)
            specific = parts[prompt_index] if prompt_index < len(parts) else ""
            description = descriptions[image_index] if descriptions and image_index is not None else ""
            text = "\n\n".join(s.strip() for s in (_text(prompt), description, specific) if s.strip())
            for position in range(a, b, max_clip_frames):
                keep = min(max_clip_frames, b - position)
                clips.append(H3Clip(position, keep, aligned_h3_length(keep), scene_index, text,
                                    source_index=source_index, image_index=image_index))
            scene_index += 1
        output_start = output_end
    if prompt_timing and any(text.strip() and index not in used_prompts for index, text in enumerate(parts)):
        raise ValueError("Some scene prompts have no clip. Match the first/next prompt list to the cut times.")
    total = output_start
    excerpt = audio.get("eclipse_excerpt") if audio is not None else None
    audio = fit_soundtrack(audio, total)
    report = _plan_report(clips, total, source)
    report += f" {len(spans)} source clips; images cycle by source clip, not scene. Audio is soundtrack only."
    if len(frames) > len(spans):
        report += f" {len(frames) - len(spans)} extra images are unused."
    if cuts and cuts[-1] >= spans[-1][2]:
        report += " Cuts outside the source timeline are ignored."
    return H3ClipPlan(tuple(clips), total, source, audio, report, soundtrack_only=True,
                      source_metadata={"clips": metadata, "duration_override": duration, "audio_excerpt": excerpt})


def add_source_boundaries(scene_plan, video):
    """Insert playlist cuts after scene-cut limiting and before LLM sampling."""
    from .scene_analysis import ScenePlan

    if not isinstance(scene_plan, ScenePlan):
        raise TypeError("Expected a Scene Detector plan.")
    timing = scene_plan.source.timing
    times = (*timing.timestamps, timing.duration)
    spans = source_spans(video, timing.duration)
    cuts = {scene["start_frame"] for scene in scene_plan.scenes}
    cuts.update(bisect_left(times, start) for _, start, _ in spans)
    boundaries = sorted(cuts | {len(timing)})
    scenes = tuple({"scene_id": i, "start_frame": start, "end_frame_exclusive": end,
                    "start_seconds": float(times[start]), "end_seconds": float(times[end]),
                    "start_time": str(times[start]), "end_time": str(times[end])}
                   for i, (start, end) in enumerate(pairwise(boundaries)))
    return ScenePlan(scene_plan.source, {**scene_plan.metadata, "source_clip_boundaries": True}, scenes)
