"""Small temporal appearance summaries for short blended scene transitions."""
from itertools import groupby

import cv2
import numpy as np


def appearance_histogram(rgb):
    # Ignore luminance so an exposure pulse alone is not a new appearance.
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    values = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256]).reshape(-1)
    return values / values.sum()


def gradual_boundaries(features, hard_cuts, window_width, min_scene_frames,
                       threshold=2.3, min_change=0.2):
    """Find persistent before/after changes outside existing hard-cut windows."""
    gap, width = window_width, 2 * window_width
    radius = gap + width
    if len(features) <= 2 * radius:
        return []
    values = np.asarray(features, dtype=np.float32)
    blocked = np.zeros(len(values), dtype=bool)
    for cut in hard_cuts:
        blocked[max(0, cut - radius):min(len(values), cut + radius + 1)] = True
    candidates = []
    for index in range(radius, len(values) - radius):
        if blocked[index] or index < min_scene_frames:
            continue
        before, after = values[index - radius:index - gap], values[index + gap:index + radius]
        left, right = before.mean(axis=0), after.mean(axis=0)
        change = float(np.abs(left - right).sum()) / 2
        variation = float(np.abs(before - left).sum(axis=1).mean()
                          + np.abs(after - right).sum(axis=1).mean()) / 2
        if change >= min_change and change / max(0.01, variation) >= threshold:
            candidates.append(index)
    # One event per contiguous appearance change. Anchor it to the largest
    # adjacent histogram change in that event, not to the averaging-window edge.
    events = []
    for _, group in groupby(enumerate(candidates), lambda item: item[1] - item[0]):
        region = [index for _, index in group]
        middle = (region[0] + region[-1]) / 2
        cut = max(region, key=lambda i: (float(np.abs(values[i] - values[i - 1]).sum()), -abs(i - middle)))
        if any(abs(cut - existing) < max(min_scene_frames, radius) for existing in [*hard_cuts, *events]):
            continue
        events.append(cut)
    return events
