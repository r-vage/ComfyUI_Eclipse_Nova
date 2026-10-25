# Per-slot video layers. Timing follows the base clip; overlays never append audio.

import math
from contextlib import ExitStack
from dataclasses import dataclass
from fractions import Fraction

import numpy as np

from .video_timing import VideoTiming, check_media_interrupt

OVERLAY_MODES = {
    "opacity": "Opacity", "screen": "Screen", "remove_black": "Remove black",
    "alpha": "Alpha", "mask": "Mask video",
}
OVERLAY_DEFAULTS = {
    "target": None, "mode": "remove_black", "opacity": 1.0, "offset": 0.0,
    "threshold": 0.05, "softness": 0.1, "mask": None,
}
MAX_OVERLAYS = 8


def is_overlay(row):
    return row.get("role", "sequence") == "overlay"


def overlay_settings(row):
    return {**OVERLAY_DEFAULTS, **row.get("overlay", {})}


def validate_overlay_row(row, resolve_file):
    role = row.get("role", "sequence")
    if role not in ("sequence", "overlay"):
        raise ValueError("Clip role must be Sequence or Overlay.")
    raw = row.get("overlay", {})
    if not isinstance(raw, dict) or set(raw) - OVERLAY_DEFAULTS.keys():
        raise ValueError("Invalid video overlay settings.")
    values = overlay_settings(row)
    target = values["target"]
    if target is not None and (not isinstance(target, str) or not 0 < len(target) <= 128 or target == row["id"]):
        raise ValueError("Select another sequence clip as the overlay target.")
    if not isinstance(values["mode"], str) or values["mode"] not in OVERLAY_MODES:
        raise ValueError("Select a supported overlay mode.")
    for name, minimum, maximum in (("opacity", 0, 1), ("offset", -86400, 86400),
                                   ("threshold", 0, 1), ("softness", 0, 1)):
        value = values[name]
        if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f"Overlay {name} must be between {minimum} and {maximum}.")
    if values["mask"] is not None:
        resolve_file(values["mask"])
    return values


def overlay_groups(rows):
    active = [row for row in rows if row["enabled"] and row["file"] is not None]
    groups = {row["id"]: [] for row in active if not is_overlay(row)}
    for row in active:
        if not is_overlay(row):
            continue
        settings = overlay_settings(row)
        target = settings["target"]
        if target not in groups:
            raise ValueError(f"Overlay {row['file']['filename']}: choose an enabled Sequence target with a file.")
        if settings["mode"] == "mask" and settings["mask"] is None:
            raise ValueError(f"Overlay {row['file']['filename']}: choose a mask video.")
        groups[target].append(row)
        if len(groups[target]) > MAX_OVERLAYS:
            raise ValueError(f"A sequence clip supports at most {MAX_OVERLAYS} overlay layers.")
    return groups


def composite_frame(base, layer, settings, mask=None):
    # RGB base, straight RGBA overlay. Padding is transparent for every mode.
    opacity = settings["opacity"]
    if opacity == 0:
        return base
    foreground = layer[..., :3].astype(np.float32) / 255
    alpha = layer[..., 3:4].astype(np.float32) / 255
    mode = settings["mode"]
    if mode == "remove_black":
        light = foreground.max(axis=-1, keepdims=True)
        threshold, softness = settings["threshold"], settings["softness"]
        matte = np.clip((light - threshold) / softness, 0, 1) if softness else (light > threshold)
        alpha *= matte
    elif mode == "mask":
        if mask is None:
            return base
        matte = mask[..., :3].astype(np.float32) @ np.array([.2126, .7152, .0722], dtype=np.float32) / 255
        if mask.shape[-1] == 4:
            matte *= mask[..., 3].astype(np.float32) / 255
        alpha *= matte[..., None]
    background = base.astype(np.float32) / 255
    if mode == "screen":
        foreground = 1 - (1 - background) * (1 - foreground)
    alpha *= opacity
    return np.rint(np.clip(background * (1 - alpha) + foreground * alpha, 0, 1) * 255).astype(np.uint8)


class TimedFrames:
    # Forward-only timestamp sampling, retaining one decoded frame per layer.
    def __init__(self, frames, timing):
        self.frames = iter(frames)
        self.durations = iter(timing.durations)
        self.duration = timing.duration
        self.end = Fraction()
        self.current = None

    def at(self, moment):
        if moment < 0:
            return None
        if moment >= self.duration:
            self.close()
            return None
        while self.current is None or moment >= self.end:
            check_media_interrupt()
            self.current = next(self.frames)
            self.end += next(self.durations)
        return self.current

    def close(self):
        close = getattr(self.frames, "close", None)
        if close:
            close()
        self.current = None


@dataclass
class FixedOverlaySegment:
    base: object
    timing: VideoTiming
    offset: Fraction

    @property
    def row(self):
        return self.base.row


def fixed_overlay_segments(clips, rate):
    # Partition one global output clock, avoiding per-clip rounding drift.
    position, result = Fraction(), []
    for clip in clips:
        start = math.ceil(position * rate)
        stop = math.ceil((position + clip.timing.duration) * rate)
        if stop > start:
            result.append(FixedOverlaySegment(clip, VideoTiming.constant(stop - start, rate),
                                              Fraction(start, 1) / rate - position))
        position += clip.timing.duration
    return result


def composite_frames(base, layers, masks, reader, *, output_timing=None, start=Fraction()):
    with ExitStack() as cleanup:
        source = iter(reader(base))
        cleanup.callback(source.close)
        sampler = TimedFrames(source, base.timing) if output_timing is not None else None
        if sampler:
            cleanup.callback(sampler.close)
        timing = output_timing if output_timing is not None else base.timing
        streams = []
        for layer in layers:
            settings = overlay_settings(layer.row)
            stream = TimedFrames(reader(layer, alpha=True), layer.timing)
            cleanup.callback(stream.close)
            mask_clip = masks.get(layer.row["id"])
            mask = TimedFrames(reader(mask_clip, alpha=True), mask_clip.timing) if mask_clip else None
            if mask:
                cleanup.callback(mask.close)
            # Mask time zero matches the untrimmed overlay's first frame, even
            # when the mask FPS differs. Source-frame trimming moves both clocks.
            mask_start = layer.scan.times[layer.first] - layer.scan.times[0]
            streams.append((settings, stream, mask, mask_start))
        moment = start
        for duration in timing.durations:
            check_media_interrupt()
            frame = sampler.at(moment) if sampler else next(source)
            for settings, stream, mask, mask_start in streams:
                local = moment - Fraction(str(settings["offset"]))
                pixels = stream.at(local)
                if pixels is not None:
                    mask_pixels = mask.at(mask_start + local) if mask else None
                    frame = composite_frame(frame, pixels, settings, mask_pixels)
            yield frame
            moment += duration
