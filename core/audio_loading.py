# File/incoming audio excerpts, validation and the panel's file catalog.

import hashlib
import math
import os
from numbers import Integral

import folder_paths
import torch

from .audio import load_audio_file, save_audio_preview

MISSING_AUDIO = object()
SOURCES = ("Auto", "Selected file", "Incoming audio")


def audio_files():
    try:
        return sorted(folder_paths.filter_files_content_types(
            os.listdir(folder_paths.get_input_directory()), ["audio", "video"]))
    except OSError:
        return []


def validate_audio_source(audio, audio_in=MISSING_AUDIO, source="Auto"):
    if source not in SOURCES:
        return "Select Auto, Selected file, or Incoming audio."
    if source == "Incoming audio":
        return True if audio_in is not MISSING_AUDIO else "Incoming audio requires an audio_in connection."
    if source != "Selected file" and audio_in is not MISSING_AUDIO:
        return True
    if not audio or not folder_paths.exists_annotated_filepath(audio):
        return f"Invalid audio file: {audio}"
    return True


def audio_fingerprint(audio):
    path = folder_paths.get_annotated_filepath(audio) if audio else ""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as file:
            while chunk := file.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        # Missing selected files are diagnosed by validation or execution. Auto
        # may still use connected audio when its fallback file is unavailable.
        return "missing"
    return digest.hexdigest()


def load_audio_excerpt(audio, start_time=0.0, duration=0.0, audio_in=None, stop_review=False, source="Auto"):
    if source not in ("Auto", "Selected file", "Incoming audio"):
        raise ValueError("Select Auto, Selected file, or Incoming audio.")
    if source == "Selected file":
        audio_in = None
    elif source == "Incoming audio" and audio_in is None:
        raise ValueError("Incoming audio is unavailable. Enable/connect its source or choose Selected file.")
    if not all(math.isfinite(v) and v >= 0 for v in (start_time, duration)):
        raise ValueError("start_time and duration must be finite, non-negative seconds.")
    if audio_in is not None:
        if not isinstance(audio_in, dict):
            raise ValueError("Malformed AUDIO: expected waveform and sample_rate.")
        waveform = audio_in.get("waveform")
        sample_rate = audio_in.get("sample_rate")
        if (
            not isinstance(waveform, torch.Tensor)
            or waveform.ndim != 3
            or not all(waveform.shape)
            or not waveform.is_floating_point()
        ):
            raise ValueError(
                "Malformed AUDIO: waveform must be a non-empty floating tensor "
                "[batch, channels, samples]."
            )
        if (
            isinstance(sample_rate, bool)
            or not isinstance(sample_rate, Integral)
            or sample_rate <= 0
        ):
            raise ValueError("Malformed AUDIO: sample_rate must be a positive integer.")
        if not torch.isfinite(waveform).all():
            raise ValueError("Malformed AUDIO: waveform contains non-finite samples.")
        start = round(start_time * sample_rate)
        end = waveform.shape[-1]
        if duration:
            end = min(end, start + round(duration * sample_rate))
        if start >= end:
            raise ValueError(
                "Audio excerpt is empty: start is beyond the end or duration is too short."
            )
        out = dict(audio_in, waveform=waveform[..., start:end])
        preview = save_audio_preview(waveform, sample_rate)
        ui = {"audio_source": ["incoming"], "audio_preview": [preview]}
    else:
        audio_path = folder_paths.get_annotated_filepath(audio) if audio else ""
        if not os.path.isfile(audio_path):
            raise ValueError(f"Invalid fallback audio file: {audio}")
        waveform, sample_rate = load_audio_file(
            audio_path, start_time=start_time, duration=duration
        )
        out = {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}
        if not waveform.shape[-1]:
            raise ValueError("Audio excerpt is empty.")
        ui = {"audio_source": ["file"]}
    loaded_duration = out["waveform"].shape[-1] / sample_rate
    ui["audio_trim"] = [{"start_time": start_time, "duration": duration}]
    if stop_review:
        import nodes  # type: ignore

        # ComfyUI publishes the returned UI before checking this flag at
        # the next node, matching Eclipse's existing review-stop nodes.
        nodes.interrupt_processing()
    return out, loaded_duration, ui

