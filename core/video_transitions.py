# Centered edge-frame transitions retain each clip's frames and audio clock.
from fractions import Fraction
from itertools import chain, pairwise

import torch

from .image_blending import blend_frames, resolve_blend_mode
from .video_timing import check_media_interrupt


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
