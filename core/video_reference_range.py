"""Numeric timeline durations select prefixes of the active reference clips."""
from fractions import Fraction

DURATIONS = ("Source clip lengths", "Audio track length", "Seconds per clip", "Total seconds")
RANGE_TYPE = "ECLIPSE_VIDEO_REFERENCE_RANGE"


def reference_limit(duration_source, seconds):
    if duration_source not in DURATIONS:
        raise ValueError("Choose a duration source.")
    if duration_source not in DURATIONS[2:] or seconds == -1:
        return None
    limit = Fraction(str(seconds))
    if not 0 < limit <= 86400:
        raise ValueError("Use a positive duration up to 24 hours, or −1 for the available reference.")
    return limit


def reference_lengths(lengths, duration_source, seconds):
    """Yield the retained length of each contributing clip, in playlist order."""
    limit = reference_limit(duration_source, seconds)
    if limit is None:
        yield from lengths
        return
    for length in lengths:
        retained = min(length, limit)
        yield retained
        if duration_source == "Total seconds":
            limit -= retained
            if not limit:
                break
