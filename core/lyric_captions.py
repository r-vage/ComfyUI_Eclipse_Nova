# Shared lyric alignment and rendering for the native and structured caption nodes.
import json
from pathlib import Path

from .fonts import get_font_path
from .logger import log
from .lyric_alignment import (
    ALGORITHM_REVISION,
    cached_alignment,
    model_identity,
)
from .lyric_animation import ANIMATED_MODES
from .lyric_render import render_video, validate_background
from .lyric_timing import (
    analysis_audio,
    audio_data,
    caption_lines,
    clean_lyrics,
    shifted_lines,
    srt_text,
    timing_coverage,
    trim_audio,
    validate_timing,
)
from .node_debug import debug_event, debug_node

_MISSING = object()
_LOG_PREFIX = "RenderLyricCaptions"


def _single(value, name):
    # ComfyUI wraps all inputs for list-aware nodes, including lazy placeholders.
    while isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise ValueError(f"{name} requires exactly one value; only background accepts a sequence.")
        value = value[0]
    return value


def _automatic_timing(value):
    # A nonempty string sentinel survives fallback switches. Only an empty
    # object requests alignment; populated or malformed JSON still validates.
    text = value.strip() if value is not None else ""
    return not text or (text.startswith("{") and text.endswith("}")
                        and not text[1:-1].strip(" \t\r\n"))


def fingerprint_inputs(font_file="", corrected_timing="", **kwargs):
    font_file = _single(font_file, "font_file")
    corrected_timing = _single(corrected_timing, "corrected_timing")
    if not isinstance(font_file, str):
        return None  # Linked widget values are resolved only during execution.
    path = Path(get_font_path(font_file))
    font = (path.stat().st_size, path.stat().st_mtime_ns) if path.is_file() else "missing"
    # Linked corrections are resolved at execution. Do not inspect model files
    # for a correction (or a link that might supply one).
    identity = model_identity() if isinstance(corrected_timing, str) and _automatic_timing(corrected_timing) else ()
    return font, identity, ALGORITHM_REVISION


def check_lazy_status(vocals=_MISSING, corrected_timing=None, **kwargs):
    vocals = _single(vocals, "vocals")
    corrected_timing = _single(corrected_timing, "corrected_timing")
    return ["vocals"] if _automatic_timing(corrected_timing) and vocals is None else []


@debug_node(_LOG_PREFIX, values=("language", "device", "mode", "rotation_axis", "position",
                                "unmatched_passages"))
def render_captions(
    audio, lyrics, trim_start, duration, language="en", device="auto", vocals=None,
    corrected_timing="", timing_adjustment=0, background=None, unmatched_passages="omit", word_timing="whisper", **settings,
):
    audio, lyrics, trim_start, duration, language, device, vocals, corrected_timing, timing_adjustment = (
        _single(value, name) for name, value in (
            ("audio", audio), ("lyrics", lyrics), ("trim_start", trim_start),
            ("duration", duration), ("language", language), ("device", device),
            ("vocals", vocals), ("corrected_timing", corrected_timing),
            ("timing_adjustment", timing_adjustment),
        )
    )
    settings = {name: _single(value, name) for name, value in settings.items()}
    unmatched_passages = _single(unmatched_passages, "unmatched_passages")
    if unmatched_passages not in ("omit", "transcribe"):
        raise ValueError("Unmatched passages must be omit or transcribe.")
    validate_background(background)
    text, removed = clean_lyrics(lyrics)
    waveform, rate = audio_data(audio)
    full_duration = waveform.shape[-1] / rate
    clipped, actual_start = trim_audio(audio, trim_start, duration)
    if not _automatic_timing(corrected_timing):
        debug_event(_LOG_PREFIX, "Using corrected timing; bypassing recognition")
        data = validate_timing(corrected_timing, text)
        if abs(data["duration"] - full_duration) > 0.05:
            raise ValueError("Corrected timing duration must match the full audio, before trimming.")
        report = {"source": "corrected timing; inference bypassed", "analysis_source": "corrected timing (no audio analysis)",
                  "algorithm_revision": ALGORITHM_REVISION, "cache_hit": False,
                  "language": data.get("language"), "warnings": []}
    else:
        debug_event(_LOG_PREFIX, "Resolving lyric alignment", isolated_vocals=vocals is not None)
        source, source_name = analysis_audio(audio, vocals)
        data, report = cached_alignment(
            source, text, language, device, source_name,
            **({"fallback_audio": audio} if vocals is not None else {}),
            **({"transcribe_unmatched": True} if unmatched_passages == "transcribe" else {}),
        )
        from .lyric_qwen import refine_timing

        data, comparison = refine_timing(audio, data, _single(word_timing, "word_timing"), device, vocals, language)
        if comparison is not None:
            report["word_timing"] = comparison
            report.setdefault("warnings", []).extend(comparison["warnings"])
    # A resampled stem may differ by a sample, or within the allowed 50 ms.
    # Clamp timings at the original soundtrack end without shifting/stretching.
    data["duration"] = full_duration
    for line in [*data["lines"], *data.get("extra_occurrences", []), *data.get("transcribed_passages", [])]:
        for item in [line, *line["words"]]:
            if item["start"] is not None:
                item["end"] = min(item["end"], full_duration)
                if item["start"] >= item["end"]:
                    item["start"] = item["end"] = None
    data = validate_timing(data, text)
    clip_duration = clipped["waveform"].shape[-1] / rate
    lines = shifted_lines(data, clip_duration, actual_start, timing_adjustment)
    log.msg("RenderLyricCaptions", f"Full audio: {full_duration:.3f}s; output: {clip_duration:.3f}s; sample-boundary start: {actual_start:.6f}s; analysis: {report['analysis_source']}; cache hit: {report['cache_hit']}.")
    animated = settings.get("mode", "floating-words") in ANIMATED_MODES
    full_schedule = animated or settings.get("line_max_words", 0) > 0
    # Schedule against untouched full-song times. SRT alone uses clipped
    # intervals; fades keep their phase and line splits keep their boundaries
    # even when the trim starts halfway through a displayed phrase.
    video, warnings = render_video(
        clipped, caption_lines(data) if full_schedule else lines,
        time_offset=actual_start - timing_adjustment if full_schedule else 0,
        background=background, **settings,
    )
    coverage = timing_coverage(data["lines"])
    if coverage["partial_lines"]:
        warnings.append("Partially timed lines preserve their supported caption bounds; unresolved words are not highlighted.")
    if coverage["unaligned_lines"]:
        warnings.append("Unresolved lines are omitted from captions, not classified as absent from the recording. Supply corrected timing JSON to restore them.")
    report.update(coverage)
    report["extra_occurrences"] = [
        {key: line[key] for key in ("source_line", "text", "start", "end")}
        for line in data.get("extra_occurrences", [])
    ]
    report["transcribed_passages"] = [
        {key: line[key] for key in ("text", "start", "end")}
        for line in data.get("transcribed_passages", [])
    ]
    report.update(duration=clip_duration, full_audio_duration=full_duration,
                  trim_start=actual_start, requested_trim_start=trim_start,
                  requested_duration=duration, timing_adjustment=timing_adjustment,
                  caption_duration=sum(line["end"] - line["start"] for line in lines),
                  caption_lines=len(lines), unaligned_lines_skipped=coverage["unaligned_lines"],
                  removed_heading_count=len(removed))
    report.setdefault("warnings", []).extend(warnings)
    debug_event(_LOG_PREFIX, "Caption results", caption_lines=len(lines),
                partial_lines=len(coverage["partial_lines"]), unaligned_lines=len(coverage["unaligned_lines"]),
                warnings=len(report["warnings"]))
    return (video, srt_text(lines), json.dumps(report, ensure_ascii=False, indent=2),
                         json.dumps(data, ensure_ascii=False, indent=2), text)
