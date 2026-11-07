# Native H3 text, reference and first-last-image clips with an optional soundtrack.
import math
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import pairwise

import torch

from .image_helpers import flatten_images
from .minimax_h3_segment_plan import (
    aligned_h3_length,
    audio_shape,
    is_h3_frame_count,
    parse_manual_transition_times,
)

CLIP_PLAN_TYPE = "ECLIPSE_H3_CLIP_PLAN"
REFERENCE_MODES = ("first_and_last", "first_only", "last_only", "adjacent_pairs",
                   "reference_images", "text_only", "first_per_scene")
FPS = 24


@dataclass(frozen=True)
class H3Clip:
    start: int
    keep: int
    render: int
    part: int
    prompt: str


@dataclass(frozen=True)
class H3ClipPlan:
    clips: tuple[H3Clip, ...]
    total_frames: int
    audio_source: str
    audio: dict | None = field(repr=False)
    report: str


def _text(value):
    # A single-scene analysis has no next-part list; Join returns None for it.
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError("Clip prompts and cut times must be text.")
    return value


def plan_clips(duration, max_clip_frames, cut_times, prompt, first_prompt,
               next_prompts, audio=None, reference_video=None):
    if not is_h3_frame_count(max_clip_frames):
        raise ValueError("Max clip frames must be on H3's 17k+5 grid, from 124 to 362.")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Duration must be positive and finite.")
    source = "H3-generated audio"
    reference_duration = None
    if audio is None and reference_video is not None:
        from .video_stream import video_frame_source

        reference = video_frame_source(reference_video)
        reference_duration = reference.timing.duration
        has_audio = reference.has_audio and getattr(reference_video, "eclipse_source_has_audio", True)
        audio = reference.audio() if has_audio else None
        if audio is not None:
            source = "reference video audio"
    elif audio is not None:
        source = "loaded audio"
    if audio is not None:
        waveform, rate = audio_shape(audio)
        if waveform.ndim != 3 or waveform.shape[0] != 1 or waveform.shape[1] not in (1, 2) or not waveform.shape[-1]:
            raise ValueError("Audio must contain a nonempty [1, mono or stereo, samples] waveform.")
        seconds = Fraction(waveform.shape[-1], rate)
        # A reference's frame timeline is authoritative, including silent tails.
        if reference_duration is not None:
            seconds = reference_duration
    else:
        seconds = reference_duration if reference_duration is not None else Fraction(str(duration))
    total = max(1, math.ceil(seconds * FPS))
    requested_times = _text(cut_times).strip()
    parsed = parse_manual_transition_times(requested_times, 1, 2**63 - 1)
    all_cuts = parsed[1] if parsed else []
    cuts = [frame for frame in all_cuts if frame < total]
    parts = [_text(first_prompt).strip(), *[line.strip() for line in _text(next_prompts).splitlines() if line.strip()]]
    automatic_scenes = not requested_times and len(parts) > 1
    if automatic_scenes:
        if len(parts) > total:
            raise ValueError("The selected duration must provide at least one frame per scene prompt.")
        # Untimed scene descriptions share the total duration. Capacity splits
        # below keep their scene number, prompt and reference-image assignment.
        cuts = [index * total // len(parts) for index in range(1, len(parts))]
        all_cuts = cuts
    prompt = _text(prompt)
    clips = []
    for part, (start, end) in enumerate(pairwise([0, *cuts, total])):
        specific = parts[part] if part < len(parts) else ""
        text = " ".join(value.strip() for value in (prompt, specific) if value.strip())
        for position in range(start, end, max_clip_frames):
            keep = min(max_clip_frames, end - position)
            clips.append(H3Clip(position, keep, aligned_h3_length(keep), part, text))
    report = (f"{len(clips)} clips; {len(cuts) + 1} parts; {total} frames at 24 FPS "
              f"({total / FPS:.3f}s). Audio: {source}. "
              "Render padding is removed after sampling; cut positions stay on the shared clock.")
    if automatic_scenes:
        report += f" Distributed {len(parts)} untimed scene prompts evenly across the selected duration."
    if len(all_cuts) != len(cuts):
        report += f" Ignored {len(all_cuts) - len(cuts)} cuts at or beyond the selected duration."
    if len(clips) > len(cuts) + 1:
        report += " Long parts are split into independent clips using the same part prompt."
    if len(parts) > len(cuts) + 1:
        report += " Extra part prompts beyond the selected duration are unused."
    return H3ClipPlan(tuple(clips), total, source, audio, report)


def clip_at(plan, index):
    if not isinstance(plan, H3ClipPlan):
        raise TypeError("Expected a MiniMax H3 Clip Plan.")
    if index < 0 or index >= len(plan.clips):
        raise ValueError("Clip index is outside the plan.")
    return plan.clips[index]


def reference_pair(images, mode, part):
    if mode not in REFERENCE_MODES:
        raise ValueError("Unknown reference image mode.")
    if mode in ("reference_images", "text_only"):
        return None, None
    frames = flatten_images(images)
    if not frames:
        return None, None
    if mode == "first_only":
        return frames[0], None
    if mode == "last_only":
        return None, frames[-1]
    if mode == "first_per_scene":
        return frames[min(part, len(frames) - 1)], None
    if mode == "adjacent_pairs":
        index = min(part, len(frames) - 1)
        return frames[index], frames[index + 1] if index + 1 < len(frames) else None
    return frames[0], frames[-1] if len(frames) > 1 else None


def clip_conditioning(plan, index, clip, vae, width, height, seed,
                      reference_mode="first_and_last", images=None, audio_vae=None):
    # Keep the installed native H3 tokenization, joint latent and guide encoding.
    from comfy_extras.nodes_minimax_h3 import (
        MiniMaxH3AddGuide,
        MiniMaxH3ImageToVideo,
        MiniMaxH3ReferenceToVideo,
    )

    item = clip_at(plan, index)
    first, last = reference_pair(images, reference_mode, item.part)
    if item.keep == 1 and first is not None:
        last = None
    references = flatten_images(images) if reference_mode == "reference_images" else []
    if references:
        if len(references) > 9:
            raise ValueError("H3 reference_images supports at most 9 images; select fewer timeline slots.")
        prompt = item.prompt
        if "<Picture " not in prompt:
            tags = ", ".join(f"<Picture {i + 1}>" for i in range(len(references)))
            prompt = f"Use {tags} as visual references. {prompt}".strip()
        positive, latent = MiniMaxH3ReferenceToVideo.execute(
            clip, prompt, width, height, item.render, vae=vae,
            ref_images={f"image_{i + 1}": image for i, image in enumerate(references)},
        ).result
    else:
        positive, latent = MiniMaxH3ImageToVideo.execute(
            clip, vae, item.prompt, width, height, item.render,
            first_frame=first, last_frame=last,
        ).result
    if last is not None and item.keep != item.render:
        # The native last-image guide otherwise lands in discarded padding.
        # Copy metadata: a cached native conditioning must remain reusable.
        positive = [[embedding, {**metadata, "minimax_keyframes": [
            {**guide, "resolved_frame_index": item.keep - 1}
            if guide["resolved_frame_index"] == item.render - 1 else dict(guide)
            for guide in metadata.get("minimax_keyframes", [])
        ]}] for embedding, metadata in positive]
    if plan.audio is not None:
        if audio_vae is None:
            raise ValueError("An audio VAE is required to guide H3 with the selected soundtrack.")
        waveform, rate = audio_shape(plan.audio)
        start = round(Fraction(item.start, FPS) * rate)
        end = round(Fraction(item.start + item.keep, FPS) * rate)
        guide = waveform[..., start:end]
        padded = torch.zeros((*waveform.shape[:-1], round(Fraction(item.render, FPS) * rate)),
                             dtype=waveform.dtype, device=waveform.device)
        padded[..., :guide.shape[-1]] = guide
        positive = MiniMaxH3AddGuide.execute(
            positive, latent, 0, audio_vae=audio_vae,
            audio={"waveform": padded, "sample_rate": rate},
        ).result[0]
    return positive, latent, item.keep, (seed + index) % (2**64)
