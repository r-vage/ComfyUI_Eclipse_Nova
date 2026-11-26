# Centered edge-frame transitions retain each clip's frames and audio clock.
import os
import tempfile
from contextlib import closing
from dataclasses import dataclass
from fractions import Fraction
from itertools import chain, islice, pairwise

import torch

from .image_blending import blend_frames, resolve_blend_mode
from .video_timing import (
    VideoTiming,
    _rgb_array,
    check_media_interrupt,
    encode_timed_video,
)


def transition_windows(clips, mode, duration):
    windows = []
    position = Fraction()
    for first, second in pairwise(clips):
        position += first.timing.duration
        choice = first.row.get("blend_mode", "inherit")
        seconds = duration if choice == "inherit" else first.row.get("blend_duration", 1.0)
        choice = mode if choice == "inherit" else choice
        half = min(Fraction(str(seconds)) / 2, first.timing.duration / 2, second.timing.duration / 2)
        if choice == "cut":
            half = Fraction()
        windows.append({"mode": resolve_blend_mode(choice) if half else "cut", "half": half, "cut": position})
    return windows


def transition_frames(clips, reader, windows):
    # Only the current decoder, next clip's first frame and previous clip's last
    # frame are retained. The incoming edge holds before the cut; the outgoing
    # edge holds after it. This avoids trimming/repeating the soundtrack.
    iterators = [iter(reader(clip)) for clip in clips]
    previous = upcoming = None
    generator = torch.Generator(device="cpu").manual_seed(0)
    try:
        for index, clip in enumerate(clips):
            iterator = iterators[index]
            first = upcoming if upcoming is not None else next(iterator)
            outgoing = windows[index] if index < len(windows) else None
            incoming = windows[index - 1] if index else None
            upcoming = next(iterators[index + 1]) if outgoing and outgoing["half"] else None
            position = Fraction()
            for current, duration in zip(chain((first,), iterator), clip.timing.durations, strict=True):
                check_media_interrupt()
                moment = position + duration / 2
                position += duration
                source = target = None
                if incoming and incoming["half"] and moment < incoming["half"]:
                    source, target = previous, current
                    alpha, mode = float(.5 + moment / (2 * incoming["half"])), incoming["mode"]
                elif outgoing and outgoing["half"] and moment > clip.timing.duration - outgoing["half"]:
                    source, target = current, upcoming
                    alpha = float(.5 + (moment - clip.timing.duration) / (2 * outgoing["half"]))
                    mode = outgoing["mode"]
                if source is None:
                    yield current
                else:
                    left = torch.from_numpy(source.copy()).unsqueeze(0).float() / 255
                    right = torch.from_numpy(target.copy()).unsqueeze(0).float() / 255
                    result = blend_frames(left, right, torch.tensor(alpha).view(1, 1, 1, 1), mode, generator=generator)
                    yield result[0].clamp(0, 1).mul(255).round().to(torch.uint8).numpy()
                    del left, right, result
            previous = current
    finally:
        for iterator in iterators:
            if hasattr(iterator, "close"):
                iterator.close()


@dataclass
class _SceneRange:
    start: int
    timing: VideoTiming
    row: dict


def render_scene_transitions(source, context=None, audio=None, *, preview=False):
    """Composite the delivery copy. The loop and saved parts keep their original pixels."""
    from .video_helpers import TemporaryVideo
    from .video_stream import video_frame_source

    settings = (context or {}).get("video_transitions", {})
    effects = {row["frame"]: row for row in settings.get("scene_transitions", ())
               if row["picture"] != "cut" and row["seconds"] > 0}
    if not effects:
        return source
    media = video_frame_source(source, preserve_audio_format=True)
    count = len(media.timing)
    if not any(frame < count for frame in effects):
        return source
    breaks = [0, *(f for f in settings["scene_boundaries"] if 0 < f < count), count]
    spans = []
    for start, end in pairwise(breaks):
        effect = effects.get(end) if end < count else None
        row = {"blend_mode": effect["picture"], "blend_duration": effect["seconds"]} if effect else {}
        spans.append(_SceneRange(start, VideoTiming(media.timing.durations[start:end]), row))
    windows = transition_windows(spans, "cut", 0)
    # The compositor needs one future edge before the main reader has reached it.
    # A second forward-only reader avoids buffering a whole full-resolution scene.
    edge_starts = {span.start for span, window in zip(spans[1:], windows, strict=True) if window["half"]}

    def pixels():
        for frame in media.frames():
            yield _rgb_array(frame.float() if isinstance(frame, torch.Tensor) and frame.dtype == torch.bfloat16 else frame)

    import folder_paths

    fd, path = tempfile.mkstemp(prefix="EclipseTransitions_", suffix=".mp4" if preview else ".mov",
                                dir=folder_paths.get_temp_directory())
    os.close(fd)
    try:
        with closing(pixels()) as stream, closing(pixels()) as edges:
            edge_position = 0

            def reader(span):
                nonlocal edge_position
                size = len(span.timing)
                if span.start in edge_starts:
                    edge = next(islice(edges, span.start - edge_position, None))
                    edge_position = span.start + 1
                    yield edge
                    next(stream)
                    size -= 1
                yield from islice(stream, size)

            soundtrack = audio if audio is not None else media.audio()
            encode_timed_video(transition_frames(spans, reader, windows), media.timing, soundtrack, path,
                               width=media.width, height=media.height, lossless=not preview, preset="ultrafast")
        return TemporaryVideo(path, preview_compatible=preview)
    except BaseException:
        os.unlink(path)
        raise
