# One reference-based timing path for supplied lyrics and automatic transcripts.
import copy
import hashlib
import json
from collections import Counter
from contextlib import ExitStack
from difflib import SequenceMatcher

from . import lyric_alignment as alignment
from .audio_transcription import transcription_reference
from .lyric_cache import TimingCache, audio_key
from .lyric_timing import (
    analysis_audio,
    audio_data,
    caption_lines,
    clean_lyrics,
    from_alignment,
    timing_coverage,
    validate_timing,
)

REFERENCE_REVISION = "shared-lyric-reference-v3"
_ALIGNMENT_CACHE = TimingCache()


def optional_text(value, name):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text.")
    return clean_lyrics(value)[0] if value.strip() else ""


def timing_value(value, duration, name):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    decoded = json.loads(value) if isinstance(value, str) else value
    if decoded == {}:
        return None
    data = validate_timing(decoded)
    if abs(data["duration"] - duration) > 0.05:
        raise ValueError(f"{name} must match the full audio duration before trimming.")
    return data


def reference_text(data):
    return "\n".join(line["text"] for line in data["lines"])


def _normalized(text):
    return "".join(char for char in text.casefold() if char.isalnum())


def reference_changes(reference, text):
    # Match whole lines in sequence. Do not assign timestamps by row number:
    # insertions, reordered phrases and ambiguous repetitions need recovery.
    old = [(i, line) for i, line in enumerate(reference["lines"], 1) if line["text"].strip()]
    new = [(i, line) for i, line in enumerate(text.split("\n"), 1) if line.strip()]
    before, after = [line["text"] for _, line in old], [line for _, line in new]
    old_counts, new_counts = Counter(before), Counter(after)
    blocks = SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
    reused, edits = {}, []
    for kind, a, b, c, d in blocks:
        if kind == "equal":
            for (_, line), (index, _) in zip(old[a:b], new[c:d]):
                if line["start"] is not None and old_counts[line["text"]] == new_counts[line["text"]]:
                    reused[index] = copy.deepcopy(line)
            continue
        if kind != "replace" or b - a != d - c:
            continue
        for (source_index, line), (index, replacement) in zip(old[a:b], new[c:d]):
            # A nearby wording correction needs recognizable shared text and
            # cannot borrow a different existing occurrence's phrase window.
            similarity = SequenceMatcher(None, _normalized(line["text"]), _normalized(replacement), autojunk=False).ratio()
            if (line["start"] is None or similarity < 0.45
                    or replacement in old_counts or line["text"] in new_counts):
                continue
            following = [item["start"] for item in caption_lines(reference)
                         if item["start"] is not None and item["start"] >= line["end"]]
            end = min(reference["duration"], line["end"] + 1.0, min(following, default=reference["duration"]))
            edits.append({"line": index, "source_line": source_index, "text": replacement,
                          "start": line["start"], "end": end, "observed_end": line["end"]})
    return reused, edits


def _observations(reference):
    result = []
    for line in caption_lines(reference):
        words = [{"word": word["text"], "start": word["start"], "end": word["end"]}
                 for word in line["words"] if word["start"] is not None]
        if not words and line["start"] is not None:
            # Phrase-only references remain a single observed interval.
            words = [{"word": line["text"], "start": line["start"], "end": line["end"]}]
        result.append({"text": line["text"], "start": line["start"], "end": line["end"], "words": words})
    return result


def _align_edits(model, samples, edits, duration, language):
    import comfy.model_management as mm

    if not edits:
        return {}, []
    mm.throw_exception_if_processing_interrupted()
    ordered = sorted(edits, key=lambda item: item["start"])
    result = model.align_words(
        samples, [{key: item[key] for key in ("text", "start", "end")} for item in ordered],
        language=language, normalize_text=False, regroup=False, verbose=None, suppress_silence=True,
    )
    mm.throw_exception_if_processing_interrupted()
    segments = result.to_dict()["segments"] if result is not None else [{"words": []} for _ in ordered]
    if len(segments) != len(ordered):
        raise ValueError("Word alignment changed the corrected phrase count; supply corrected timing JSON.")
    aligned, phrase_only = {}, []
    for edit, segment in zip(ordered, segments):
        segment = copy.deepcopy(segment)
        for word in segment.get("words", []):
            if (word.get("start") is None or word.get("end") is None
                    or not edit["start"] <= word["start"] < word["end"] <= edit["end"] + 0.001):
                word["start"] = word["end"] = None
        line = from_alignment(edit["text"], {"segments": [segment]}, duration, language)["lines"][0]
        if line["start"] is None:
            # Keep the observed phrase readable, without inventing word timing.
            line.update(start=edit["start"], end=edit["observed_end"], timing_source="reference phrase")
            phrase_only.append(edit["line"])
        # Search padding is never a caption end. Only observed/aligner times are.
        aligned[edit["line"]] = line
    return aligned, phrase_only


def align_reference(model, samples, reference, text, language, fallback_samples=None, *, transcribe_unmatched=False):
    reused, edits = reference_changes(reference, text)
    # With a known phrase window the original soundtrack retains sung tails
    # that separation can remove. Initial recognition still uses selected vocals.
    edit_samples = fallback_samples if fallback_samples is not None else samples
    edited, phrase_only = _align_edits(model, edit_samples, edits, reference["duration"], language)
    preserved = {**reused, **edited}
    data, details = alignment.anchored_alignment(
        model, samples, text, language, fallback_samples, transcribe_unmatched=transcribe_unmatched,
        initial_observations=_observations(reference), preserved_lines=preserved,
        reference_duration=reference["duration"],
    )
    details["reference"] = {
        "reused_lines": sorted(reused), "corrected_lines": sorted(edited),
        "phrase_only_corrections": phrase_only,
        "correction_audio": "original mix" if fallback_samples is not None else "analysis audio",
    }
    return validate_timing(data, text), details


def _resolve_timing(audio, lyrics=None, corrected_lyrics=None, timing=None, corrected_timing=None,
                   vocals=None, language="Auto", device="auto", unmatched_passages="omit"):
    import comfy.model_management as mm

    mm.throw_exception_if_processing_interrupted()
    waveform, rate = audio_data(audio)
    full_duration = waveform.shape[-1] / rate
    original = optional_text(lyrics, "Lyrics")
    corrected = optional_text(corrected_lyrics, "Corrected lyrics")
    manual = timing_value(corrected_timing, full_duration, "Corrected timing")
    if manual is not None:
        text = corrected or original or reference_text(manual)
        try:
            data = validate_timing(manual, text)
        except ValueError as error:
            raise ValueError("Corrected timing must match the selected lyrics. Clear corrected_timing to align wording edits automatically.") from error
        return text, data, {"source": "manual timing", "analysis_source": "manual timing (no audio analysis)",
                            "cache_hit": False, "warnings": [], "algorithm_revision": REFERENCE_REVISION}

    reference = timing_value(timing, full_duration, "Original timing")
    with ExitStack() as stack:
        session = None
        transcript_report = None
        if reference is None:
            _text, reference, transcript_report, session = stack.enter_context(
                transcription_reference(audio, language, device, vocals))
        baseline = original or reference_text(reference)
        text = corrected or baseline
        if not text.strip():
            raise ValueError("No lyrics were supplied or recognized. Add lyrics or review the audio/language.")
        report = {"source": "reference timing", "algorithm_revision": REFERENCE_REVISION,
                  "analysis_source": "reference timing (no new audio analysis)", "cache_hit": False,
                  "warnings": [], "alignment_passes": []}
        if transcript_report is not None:
            report["transcription"] = transcript_report
            report["analysis_source"] = transcript_report["analysis_source"]
            report["warnings"].extend(transcript_report["warnings"])
        source = source_name = fallback_samples = identity = None

        def aligned_to(data, target):
            nonlocal session, source, source_name, fallback_samples, identity
            if reference_text(data) == target:
                report["alignment_passes"].append({"method": "reuse unchanged timing", "reused_lines": len(data["lines"])})
                return copy.deepcopy(data)
            if source is None:
                source, source_name = analysis_audio(audio, vocals)
                identity = (audio_key(audio, vocals), device, str(alignment.model_path()), alignment.model_identity(),
                            alignment.MODEL_REVISION, alignment.ALGORITHM_REVISION, REFERENCE_REVISION)
            selected_language = language
            if language == "Auto" and data.get("language") in alignment.LANGUAGES:
                selected_language = data["language"]
            key = (*identity, selected_language, target, unmatched_passages,
                   hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest())
            result = _ALIGNMENT_CACHE.get(key)
            hit = result is not None
            if not hit:
                if session is None:
                    session = stack.enter_context(alignment.recognition_model(source, selected_language, device))
                model, samples, detected_language, _detection = session
                if vocals is not None and fallback_samples is None:
                    import torchaudio.functional as AF

                    fallback_samples = AF.resample(waveform.mean(0), rate, 16000).numpy()
                result = align_reference(model, samples, data, target, detected_language, fallback_samples,
                                         transcribe_unmatched=unmatched_passages == "transcribe")
                mm.throw_exception_if_processing_interrupted()
                if any(line["start"] is not None for line in caption_lines(result[0])):
                    _ALIGNMENT_CACHE.put(key, result)
            report["cache_hit"] = hit
            report["analysis_source"] = source_name
            report["alignment_passes"].append({"cache_hit": hit, **result[1]})
            return result[0]

        # Supplied original lyrics can have different line breaks than ASR.
        # Establish their reference once; edits reuse it on subsequent queues.
        if baseline and baseline != text:
            reference = aligned_to(reference, baseline)
        data = aligned_to(reference, text)
        data["duration"] = full_duration
        for line in [*data["lines"], *data.get("extra_occurrences", []), *data.get("transcribed_passages", [])]:
            for item in [line, *line["words"]]:
                if item["start"] is not None:
                    item["end"] = min(item["end"], full_duration)
                    if item["start"] >= item["end"]:
                        item["start"] = item["end"] = None
        report.update(timing_coverage(data["lines"]))
        report["warnings"].append("Word alignment is estimated; review corrected phrases, repeats and sustained notes in the timing preview.")
        return text, validate_timing(data, text), report


def resolve_timing(audio, lyrics=None, corrected_lyrics=None, timing=None, corrected_timing=None,
                   vocals=None, language="Auto", device="auto", unmatched_passages="omit", word_timing="whisper"):
    from .lyric_qwen import refine_timing

    # Exit the Whisper session before loading another model. Manual timing is
    # authoritative and must not load either aligner or inspect unused vocals.
    text, data, report = _resolve_timing(audio, lyrics, corrected_lyrics, timing, corrected_timing,
                                       vocals, language, device, unmatched_passages)
    if report["source"] != "manual timing":
        data, comparison = refine_timing(audio, data, word_timing, device, vocals, language)
        if comparison is not None:
            report["word_timing"] = comparison
            if "analysis_source" in comparison:
                report["analysis_source"] = comparison["analysis_source"]
            report["warnings"].extend(comparison["warnings"])
            report.update(timing_coverage(data["lines"]))
    return text, data, report
