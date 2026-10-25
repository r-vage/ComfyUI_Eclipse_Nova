# Hold selected images on an audio-length timeline and stream a native VIDEO.
import json
import math
import os
import tempfile
from fractions import Fraction
from itertools import pairwise

import folder_paths
import numpy as np
import torch
from PIL import Image

from .audio_timeline import (
    align_activity_gap,
    encoded_audio_activity,
    waveform_audio_activity,
)
from .image_blending import BLEND_MODES, prepare_blend, resolve_blend_mode
from .image_effects import styled_frames, validate_style
from .image_helpers import flatten_images, tensor2pil
from .video_helpers import TemporaryVideo
from .video_loader import _fit
from .video_timing import VideoTiming, check_media_interrupt, encode_timed_video


def single(value, name):
    while isinstance(value, (list, tuple)):
        if len(value) > 1:
            raise ValueError(f"Connect one {name} value for the complete image timeline.")
        value = value[0] if value else None
    return value


def audio_length(audio):
    if not isinstance(audio, dict):
        raise TypeError("Connect the original AUDIO soundtrack.")
    waveform, rate = audio.get("waveform"), audio.get("sample_rate")
    if (not isinstance(waveform, torch.Tensor) or waveform.ndim != 3 or waveform.shape[0] != 1
            or waveform.shape[1] not in (1, 2) or waveform.shape[-1] < 1 or not waveform.is_floating_point()):
        raise ValueError("Audio must be a nonempty floating tensor [1, 1 or 2, samples].")
    if type(rate) not in (int, float) or not math.isfinite(rate) or rate < 1 or int(rate) != rate:
        raise ValueError("Audio sample rate must be a positive integer.")
    return Fraction(waveform.shape[-1], int(rate))


def plan_timeline(audio, image_count, *, fps=25.0, duration=0.0, mode="Silence", manual_transition_times="",
                  audio_encoder_output=None, analysis_audio=None, transition_edge="activity_resume",
                  search_window_seconds=3.0, min_silence_duration=0.5, resume_hold_duration=0.2):
    source_duration = audio_length(audio)
    for key, value, minimum, maximum in (("fps", fps, 1, 120), ("duration", duration, 0, 86400),
                                       ("search_window_seconds", search_window_seconds, 0, 60),
                                       ("min_silence_duration", min_silence_duration, 0.02, 30),
                                       ("resume_hold_duration", resume_hold_duration, 0.02, 30)):
        if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}.")
    if mode not in ("Even", "Silence", "Manual") or transition_edge not in ("activity_resume", "silence_start"):
        raise ValueError("Unsupported transition mode or edge.")
    if type(image_count) is not int or image_count < 1:
        raise ValueError("Select at least one image.")
    if not isinstance(manual_transition_times, str):
        raise TypeError("Manual transition times must be comma-separated seconds.")
    rate = Fraction(str(fps))
    clip_duration = min(source_duration, Fraction(str(duration))) if duration else source_duration
    total = math.ceil(clip_duration * rate)
    if image_count > total:
        raise ValueError("The video is too short to show every selected image for at least one frame.")
    notes = []
    transitions = []
    if image_count == 1:
        notes.append("One image holds for the full duration; transition analysis and manual times are skipped.")
    elif mode == "Manual":
        parts = manual_transition_times.strip().split(",")
        if len(parts) != image_count - 1 or any(not value.strip() for value in parts):
            raise ValueError(f"Enter exactly {image_count - 1} manual transition times for {image_count} images.")
        try:
            times = [float(value) for value in parts]
        except ValueError as error:
            raise ValueError("Manual transition times must be comma-separated seconds.") from error
        if any(not math.isfinite(value) or not 0 < value < clip_duration for value in times):
            raise ValueError("Manual transition times must be finite and inside the audio clip.")
        transitions = [round(Fraction(str(value)) * rate) for value in times]
        if transitions != sorted(set(transitions)) or any(not 0 < value < total for value in transitions):
            raise ValueError("Manual transition times must resolve to distinct increasing frames inside the video.")
        notes.append("Manual cuts use the nearest frame; no silence adjustment is applied.")
    else:
        targets = [round(Fraction(total * index, image_count)) for index in range(1, image_count)]
        activity = None
        if mode == "Silence":
            check_media_interrupt()
            if audio_encoder_output is not None:
                activity, error = encoded_audio_activity(audio_encoder_output)
                if activity is None:
                    raise ValueError(f"Invalid audio encoder output: {error}.")
                notes.append("Quiet-gap alignment reuses connected Wav2Vec2 activity features.")
            else:
                guide = analysis_audio if analysis_audio is not None else audio
                if abs(audio_length(guide) - source_duration) > Fraction(1, 20):
                    raise ValueError("Analysis audio must have the same start and duration as the soundtrack (within 50 ms).")
                activity = waveform_audio_activity(guide)
                notes.append("Quiet-gap alignment uses waveform RMS activity; use isolated vocals for gaps between sung lines.")
            notes.append("Activity gaps are not a speech/silence classification. Unmatched targets keep even spacing.")
        for index, target in enumerate(targets):
            minimum = transitions[-1] + 1 if transitions else 1
            maximum = total - (image_count - index - 1)
            target = min(max(target, minimum), maximum)
            cut = target
            if activity is not None:
                found, details = align_activity_gap(activity, target, fps, transition_edge, search_window_seconds,
                                                    min_silence_duration, resume_hold_duration,
                                                    minimum_frame=minimum, maximum_frame=maximum)
                if found is not None:
                    cut = found
                notes.append(f"Cut {index + 1}: {target / fps:.3f}s → {cut / fps:.3f}s; {details}.")
            transitions.append(cut)
    ranges = [{"image_index": index, "start_frame": start, "end_frame": end,
               "start_seconds": float(Fraction(start, 1) / rate), "end_seconds": float(Fraction(end, 1) / rate)}
              for index, (start, end) in enumerate(pairwise([0, *transitions, total]))]
    return {"version": 1, "kind": "image_timeline", "mode": mode, "fps": float(rate), "total_frames": total,
            "audio_duration": float(clip_duration), "video_duration": float(total / rate),
            "image_count": image_count, "transition_frames": transitions, "images": ranges, "notes": notes}


def blend_windows(plan, mode, duration, options=None):
    if mode not in ("cut", *BLEND_MODES):
        raise ValueError("Unsupported image timeline blend mode.")
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 <= duration <= 60:
        raise ValueError("Blend duration must be between 0 and 60 seconds.")
    boundaries = [0, *plan["transition_frames"], plan["total_frames"]]
    windows = []
    for index, cut in enumerate(boundaries[1:-1], 1):
        row = options[index - 1] if options else {}
        selected = row.get("blend_mode", "inherit")
        chosen_mode = mode if selected == "inherit" else selected
        chosen_duration = duration if selected == "inherit" else row.get("blend_duration", 1.0)
        frames = round(Fraction(str(chosen_duration)) * Fraction(str(plan["fps"]))) if chosen_mode != "cut" else 0
        # Confine each side to half its image interval: adjacent transitions
        # cannot overlap, and the soundtrack and planned cut times never move.
        before = min(frames // 2, (cut - boundaries[index - 1]) // 2)
        after = min(frames - frames // 2, (boundaries[index + 1] - cut) // 2)
        windows.append({"image_index": index, "start_frame": cut - before, "end_frame": cut + after,
                        "blend_mode": chosen_mode, "blend_duration": chosen_duration})
    return windows


def image_options(values, count):
    if values is None:
        return [{} for _ in range(count)]
    if not isinstance(values, list) or len(values) != count:
        raise ValueError("Image slot settings must match the selected image count.")
    for value in values:
        if not isinstance(value, dict):
            raise TypeError("Expected image slot settings.")
        for key, choices, default in (("fit", ("inherit", "crop", "pad", "stretch"), "inherit"),
                                      ("crop_x", ("left", "center", "right"), "center"),
                                      ("crop_y", ("top", "center", "bottom"), "center"),
                                      ("blend_mode", ("inherit", "cut", *BLEND_MODES), "inherit")):
            if value.get(key, default) not in choices:
                raise ValueError(f"Unsupported image slot {key}.")
        duration = value.get("blend_duration", 1.0)
        if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 <= duration <= 60:
            raise ValueError("Image slot blend duration must be between 0 and 60 seconds.")
    return values


def output_dimensions(width, height, source_w, source_h):
    for value in (width, height):
        if type(value) is not int or not 0 <= value <= 8192:
            raise ValueError("Width and height must be integers between 0 and 8192; zero keeps source sizing.")
    if not width and not height:
        width, height = source_w, source_h
    elif not width:
        width = max(1, round(height * source_w / source_h))
    elif not height:
        height = max(1, round(width * source_h / source_w))
    if max(width, height) > 8192:
        raise ValueError("Resolved output dimensions must not exceed 8192 pixels.")
    return width, height


def fit_timeline_image(image, width, height, option, fit="pad", *, preserve_alpha=False):
    # Shared still-image framing; no transition, animation or global style.
    check_media_interrupt()
    if not torch.isfinite(image).all().item():
        raise ValueError("Image pixels must be finite.")
    picture = tensor2pil(image.to(dtype=torch.float32))
    if picture.mode == "RGBA" and not preserve_alpha:
        picture = Image.alpha_composite(Image.new("RGBA", picture.size, (0, 0, 0, 255)), picture)
    mode = "RGBA" if preserve_alpha and picture.mode == "RGBA" else "RGB"
    chosen_fit = option.get("fit", "inherit")
    return _fit(np.asarray(picture.convert(mode)), width, height, fit if chosen_fit == "inherit" else chosen_fit,
                crop_x={"left": 0, "center": .5, "right": 1}[option.get("crop_x", "center")],
                crop_y={"top": 0, "center": .5, "bottom": 1}[option.get("crop_y", "center")])


def render_image_video(images, audio, *, width=0, height=0, fit="pad", blend_mode="cut", blend_duration=1.0,
                       slot_settings=None, style="off", style_strength=0.5, style_period=2.0, **settings):
    style_settings = validate_style(style, style_strength, style_period)
    selected = flatten_images(images)
    if not selected:
        raise ValueError("Select at least one image.")
    for image in selected:
        if (image.ndim != 4 or image.shape[0] != 1 or any(size < 1 for size in image.shape)
                or image.shape[-1] not in (1, 3, 4) or not image.is_floating_point()):
            raise ValueError("Images must be floating HWC/BHWC tensors with 1, 3 or 4 channels.")
    if fit not in ("pad", "crop", "stretch"):
        raise ValueError("Fit must be pad, crop or stretch.")
    source_h, source_w = selected[0].shape[1:3]
    width, height = output_dimensions(width, height, source_w, source_h)
    options = image_options(slot_settings, len(selected))
    plan = plan_timeline(audio, len(selected), **settings)
    plan.update(width=width, height=height, fit=fit, **style_settings)
    windows = blend_windows(plan, blend_mode, blend_duration, options)
    for window in windows:
        if window["end_frame"] > window["start_frame"]:
            window["blend_mode"] = resolve_blend_mode(window["blend_mode"])
    plan.update(blend_mode=blend_mode, blend_duration=blend_duration, blend_windows=windows, slot_settings=options)
    has_blends = any(w["blend_mode"] != "cut" for w in windows)
    if has_blends:
        plan["notes"].append("Blends are centered on the planned cuts. Short image intervals limit their length without moving the audio clock.")

    def frames():
        current, position = fit_timeline_image(selected[0], width, height, options[0], fit), 0
        for window in windows:
            for _ in range(position, window["start_frame"]):
                yield current
            upcoming = fit_timeline_image(selected[window["image_index"]], width, height, options[window["image_index"]], fit)
            count = window["end_frame"] - window["start_frame"]
            if count:
                source = torch.from_numpy(current.copy()).unsqueeze(0).float() / 255
                target = torch.from_numpy(upcoming.copy()).unsqueeze(0).float() / 255
                # Dissolve is repeatable without changing any caller's RNG state.
                generator = torch.Generator(device="cpu").manual_seed(window["image_index"])
                transition = prepare_blend(source, target, window["blend_mode"], generator=generator)
                for index in range(count):
                    check_media_interrupt()
                    alpha = torch.tensor((index + 1) / (count + 1)).view(1, 1, 1, 1)
                    blended = transition(alpha)
                    yield blended[0].clamp(0, 1).mul(255).round().to(torch.uint8).numpy()
                del source, target, blended, transition
            current, position = upcoming, window["end_frame"]
        for _ in range(position, plan["total_frames"]):
            yield current

    # Reuse the lossless, bounded encoder used by Upscale Video. One fitted image
    # pair is retained during transitions; TemporaryVideo owns the cache lifetime.
    fd, path = tempfile.mkstemp(prefix="EclipseImageTimeline_", suffix=".mov", dir=folder_paths.get_temp_directory())
    os.close(fd)
    try:
        timing = VideoTiming.constant(plan["total_frames"], plan["fps"])
        # The covering last frame may need silence, not samples past a requested
        # excerpt. The renderer and saver both receive this same clipped track.
        samples = min(audio["waveform"].shape[-1], round(plan["audio_duration"] * audio["sample_rate"]))
        soundtrack = {**audio, "waveform": audio["waveform"][..., :samples]}
        rendered = styled_frames(frames(), timing, **style_settings)
        encode_timed_video(rendered, timing, soundtrack, path, width=width, height=height, lossless=True, preset="ultrafast")
        video = TemporaryVideo(path, preview_compatible=False)
    except BaseException:
        TemporaryVideo._remove(path)
        raise
    report = [(f"{len(selected)} image(s); {plan['total_frames']} frames at {plan['fps']:g} FPS; "
               f"{plan['video_duration']:.3f}s; {width} × {height}."), *plan["notes"]]
    report.extend(f"Image {item['image_index'] + 1}: {item['start_seconds']:.3f}–{item['end_seconds']:.3f}s "
                  f"(frames {item['start_frame']}–{item['end_frame'] - 1})." for item in plan["images"])
    if has_blends:
        report.extend(f"Blend {index + 1} ({window['blend_mode']}): {window['start_frame'] / plan['fps']:.3f}–{window['end_frame'] / plan['fps']:.3f}s "
                      f"({window['end_frame'] - window['start_frame']} frames)." for index, window in enumerate(windows))
    if style != "off":
        report.append(f"Global style: {style}, strength {style_strength:g}, period {style_period:g}s; applied to every image and transition.")
    report.append("Original audio is retained. Duration rounds up by less than one frame. Temporary video uses lossless RGB8.")
    return video, plan["video_duration"], plan["total_frames"], json.dumps(plan, ensure_ascii=False, indent=2), "\n".join(report)
