# Bounded CPU editing effects shared by image timelines and video playlists.
import math
from fractions import Fraction

import cv2
import numpy as np

TRANSITION_EFFECTS = ("ghost_zoom", "light_leak", "block_glitch", "zoom_blur", "dip_to_black")
STYLE_MODES = ("off", "cool_desaturated", "ghost_zoom", "light_leak", "block_glitch",
               "zoom_blur", "pulse_black", "black_pulse_flash", "ghost_edit", "glitch_edit")
STYLE_DEFAULTS = {"style": "off", "style_strength": 0.5, "style_period": 2.0}
EFFECT_TOOLTIPS = {
    "ghost_zoom": "Moving, enlarged translucent copies create a double-exposure transition.",
    "light_leak": "Two soft, warm-white flashes brighten the crossfade.",
    "block_glitch": "Deterministic displaced blocks, scanlines and split RGB edges surround the cut.",
    "zoom_blur": "A radial zoom and blur pulse masks the crossfade.",
    "dip_to_black": "Fade the outgoing image to black, then reveal the next image.",
}
STYLE_TOOLTIP = (
    "Applies to the entire output, including holds and transitions. Cool desaturated is a constant grade; "
    "other styles repeat at the selected period. Black pulse flash pairs warm-white flashes with black dips. "
    "Ghost edit combines the grade, ghost zoom and flashes. "
    "Glitch edit combines the grade, blocks, zoom blur, flashes and black dips. Cycles are time-based, not beat detection."
)


def validate_style(style="off", style_strength=0.5, style_period=2.0):
    if not isinstance(style, str) or style not in STYLE_MODES:
        raise ValueError("Select a supported global style.")
    for label, value, lower, upper in (("Style strength", style_strength, 0, 1),
                                       ("Style period", style_period, 0.2, 60)):
        if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError(f"{label} must be between {lower} and {upper}.")
    return {"style": style, "style_strength": style_strength, "style_period": style_period}


def _zoom(frame, scale, dx=0, dy=0):
    height, width = frame.shape[:2]
    matrix = np.array([[scale, 0, (1 - scale) * (width - 1) / 2 + dx * width],
                       [0, scale, (1 - scale) * (height - 1) / 2 + dy * height]], np.float32)
    result = cv2.warpAffine(frame, matrix, (width, height), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_REFLECT_101)
    return result[..., None] if result.ndim == 2 else result


def _ghost(frame, amount, phase):
    direction = math.sin(phase * math.tau)
    return ((1 - .48 * amount) * frame
            + .3 * amount * _zoom(frame, 1.15, .035 * direction, -.02)
            + .18 * amount * _zoom(frame, 1.32, -.045 * direction, .02))


def _flash(frame, amount, phase):
    # Two soft flashes, with a moving warm edge rather than flat white frames.
    pulse = max(math.exp(-((phase - .38) / .055) ** 2), math.exp(-((phase - .62) / .055) ** 2))
    x = np.linspace(0, 1, frame.shape[1], dtype=np.float32)[None, :, None]
    mask = np.clip(amount * pulse * (.65 + .35 * np.cos((x - phase) * math.pi)), 0, 1)
    color = np.ones(frame.shape[-1], dtype=np.float32)
    if len(color) >= 3:
        color[:3] = (1, .96, .9)
    return frame * (1 - mask) + color * mask


def _glitch(frame, amount, tick):
    if amount <= 0:
        return frame
    height, width = frame.shape[:2]
    result = frame.copy()
    rng = np.random.default_rng(int(tick) % (2**32))
    for _ in range(7):
        y, x = rng.integers(height), rng.integers(width)
        h, w = max(1, round(height * rng.uniform(.025, .16))), max(1, round(width * rng.uniform(.12, .7)))
        shift = round(width * rng.uniform(-.12, .12) * amount)
        result[y:y+h, x:x+w] = np.roll(frame[y:y+h], shift, axis=1)[:, x:x+w]
    if frame.shape[-1] >= 3:
        shift = max(1, round(width * .008 * amount))
        result[..., 0] = np.roll(result[..., 0], shift, axis=1)
        result[..., 2] = np.roll(result[..., 2], -shift, axis=1)
    result[::3] *= 1 - .18 * amount
    return frame * (1 - amount) + result * amount


def _zoom_blur(frame, amount):
    result = frame.copy()
    for index in range(1, 6):
        result += _zoom(frame, 1 + .035 * index * amount)
    return result / 6


def transition_effect(first, second, alpha, mode):
    # Float HWC frames. Keep alpha channels as a plain dissolve; colour effects
    # must not introduce holes when the overlap node receives RGBA images.
    if alpha <= 0:
        return first
    if alpha >= 1:
        return second
    eased = alpha * alpha * (3 - 2 * alpha)
    base = first * (1 - eased) + second * eased
    color = base[..., :3] if base.shape[-1] == 4 else base
    amount = math.sin(math.pi * alpha) ** 2
    if mode == "dip_to_black":
        color = first[..., :color.shape[-1]] * max(0, 1 - 2 * alpha) + second[..., :color.shape[-1]] * max(0, 2 * alpha - 1)
    elif mode == "ghost_zoom":
        color = _ghost(color, amount, alpha)
    elif mode == "light_leak":
        color = _flash(color, 1, alpha)
    elif mode == "block_glitch":
        color = _glitch(color, amount, int(alpha * 16))
    elif mode == "zoom_blur":
        color = _zoom_blur(color, amount)
    else:
        raise ValueError(f"Unsupported transition effect: {mode}")
    if base.shape[-1] == 4:
        color = np.concatenate((color, base[..., 3:]), axis=-1)
    return np.clip(color, 0, 1)


def style_frame(frame, seconds, *, style="off", style_strength=0.5, style_period=2.0):
    # One uint8 RGB frame in/out. No video-sized arrays, history or global RNG.
    if style == "off" or style_strength == 0:
        return frame
    phase = (float(seconds) / style_period) % 1
    strength = style_strength
    color = frame.astype(np.float32) / 255
    if style in ("cool_desaturated", "ghost_edit", "glitch_edit"):
        gray = color @ np.array([.2126, .7152, .0722], np.float32)
        graded = (color * .55 + gray[..., None] * .45) * np.array([.8, .86, .94], np.float32)
        color = color * (1 - strength) + graded * strength
    pulse = math.sin(math.pi * phase) ** 4
    if style in ("ghost_zoom", "ghost_edit"):
        color = _ghost(color, pulse * strength, phase)
    if style in ("zoom_blur", "glitch_edit"):
        color = _zoom_blur(color, pulse * strength)
    if style in ("block_glitch", "glitch_edit"):
        color = _glitch(color, pulse * strength, math.floor(float(seconds) * 12))
    if style in ("light_leak", "black_pulse_flash", "ghost_edit", "glitch_edit"):
        color = _flash(color, strength, phase)
    if style in ("pulse_black", "black_pulse_flash", "glitch_edit"):
        dip = math.exp(-((phase - .92) / .045) ** 4)
        color *= 1 - strength * dip
    return np.clip(color * 255, 0, 255).round().astype(np.uint8)


def styled_frames(frames, timing, **settings):
    settings = validate_style(**settings)
    iterator = iter(frames)
    position = Fraction()
    previous = rendered = None
    try:
        for frame, duration in zip(iterator, timing.durations, strict=True):
            # Still-image holds share one array. Reuse constant grading while
            # moving styles continue to follow the uninterrupted output clock.
            if frame is not previous or settings["style"] != "cool_desaturated":
                rendered = style_frame(frame, position, **settings)
            previous = frame
            yield rendered
            position += duration
    finally:
        if hasattr(iterator, "close"):
            iterator.close()
