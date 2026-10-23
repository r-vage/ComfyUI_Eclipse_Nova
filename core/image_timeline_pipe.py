# Media and numeric overrides for the compact Image Timeline Video panel.
import json

from .image_helpers import flatten_images
from .image_timeline_video import render_image_video, single

OVERRIDES = ("width", "height", "fps", "duration", "manual_transition_times")


def fields():
    return [
        ("images", "Image", "Ordered images from Image Selector, a batch or a list. Leave disconnected when the PIPE already supplies images. Passing the same ordered images preserves per-image options; replacement images clear them."),
        ("audio", "Audio", "Original soundtrack. Its duration bounds the timeline and its audio is retained."),
        ("audio_encoder_output", "AudioEncoderOutput", "Optional Wav2Vec2 activity from the same recording for Silence mode. Skipped for one image."),
        ("analysis_audio", "Audio", "Optional vocals for waveform gap detection when no encoder features are supplied. Same start and duration as audio; never replaces the soundtrack."),
        ("width", "Int", "Override panel width. Zero uses source sizing."),
        ("height", "Int", "Override panel height. Zero uses source sizing."),
        ("fps", "Float", "Override panel FPS; share it with lyric rendering."),
        ("duration", "Float", "Override duration; zero uses all audio. After rendering, the actual video duration."),
        ("manual_transition_times", "String", "Override manual cuts with comma-separated seconds. An empty string clears an inherited value."),
        ("video", "Video", "Completed video with original audio, ready for caption rendering or saving."),
        ("total_frames", "Int", "Completed video's frame count."),
        ("plan", "String", "JSON timeline including image intervals and actual blend windows."),
        ("report", "String", "Human-readable timeline and blend report."),
    ]


def assemble_pipe(pipe=None, **values):
    inherited = single(pipe, "pipe")
    if inherited is not None and not isinstance(inherited, dict):
        raise ValueError("Expected a PIPE dictionary from IO Image Timeline.")
    context = dict(inherited or {})
    for key, _kind, _tip in fields():
        value = values.get(key)
        if key == "images":
            value = flatten_images(value) or None
        else:
            value = single(value, key)
        if value is not None:
            if key == "images" and "image_timeline_slots" in context:
                previous = flatten_images(context.get("images"))
                # Flattening creates tensor views. Compare their storage/layout,
                # not Python identity or pixel content, without copying images.
                unchanged = len(value) == len(previous) and all(
                    current.dtype == old.dtype and current.is_set_to(old)
                    for current, old in zip(value, previous)
                )
                if not unchanged:
                    context.pop("image_timeline_slots", None)
            context[key] = value
    return context


def render_pipe(pipe, parameters):
    context = assemble_pipe(pipe)
    settings = {**parameters, **{key: context[key] for key in OVERRIDES if context.get(key) is not None}}
    video, duration, total, plan, report = render_image_video(
        context.get("images"), context.get("audio"),
        slot_settings=context.get("image_timeline_slots"),
        audio_encoder_output=context.get("audio_encoder_output"), analysis_audio=context.get("analysis_audio"), **settings,
    )
    used = json.loads(plan)
    return {**context, **{key: settings[key] for key in OVERRIDES},
            "width": used["width"], "height": used["height"], "fps": used["fps"],
            "video": video, "duration": duration, "total_frames": total, "plan": plan, "report": report}
