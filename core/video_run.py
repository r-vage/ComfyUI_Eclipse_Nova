# Persistent, relocatable video runs. Loading never owns or deletes saved files.
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from .json_store import read_json_object, write_json_object

STORAGE_TYPE = "ECLIPSE_VIDEO_STORAGE"
MANIFEST = "run.json"
NO_SAVED_RUNS = "(no saved runs found)"


def available_video_runs():
    # Discover manifests only; never load pixel arrays or claim file ownership.
    import folder_paths

    root = Path(folder_paths.get_output_directory())
    runs = []
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = [name for name in folders if not name.startswith(".")]
        if MANIFEST not in files:
            continue
        try:
            with (Path(directory) / MANIFEST).open(encoding="utf-8") as stream:
                value = json.load(stream)
            if (not isinstance(value, dict) or value.get("format") != "eclipse_video_run"
                    or value.get("version") != 1 or value.get("kind") not in ("frames", "clips")
                    or not isinstance(value.get("chunks"), list) or not value["chunks"]):
                continue
        except (OSError, ValueError):
            continue
        runs.append((Path(directory) / MANIFEST).relative_to(root).as_posix())
        folders[:] = []
    return sorted(runs, reverse=True) or [NO_SAVED_RUNS]


@dataclass(frozen=True)
class VideoStorage:
    mode: str = "temporary"
    directory: str = "video_runs"
    run_mode: str = "New run"
    run_directory: str | None = None

    def __post_init__(self):
        if self.mode not in ("memory", "temporary", "persistent"):
            raise ValueError("Choose memory, temporary or persistent video storage.")
        if self.run_mode not in ("New run", "Resume saved run", "Load saved run"):
            raise ValueError("Choose New run, Resume saved run or Load saved run.")


@dataclass(frozen=True)
class StoredDirectory:
    name: str

    def cleanup(self):
        # Only the writer calls this on a newly created, incomplete chunk.
        shutil.rmtree(self.name)


def create_run_directory(storage):
    import folder_paths

    if storage.run_directory is not None:
        root = Path(storage.run_directory)
        if not root.is_dir():
            raise ValueError("The active run folder is missing; start or resume a new queue.")
        return str(root)
    root = Path(storage.directory).expanduser()
    if not root.is_absolute():
        root = Path(folder_paths.get_output_directory()) / root
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_")
    return tempfile.mkdtemp(prefix=stamp, dir=root)


def _save_array(path, array):
    fd, name = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            np.save(stream, array, allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_run(run_directory, *, kind, fps, width, height, entries, audio=None, dtype=None,
             channels=3, metadata=None):
    root = Path(run_directory)
    total = 0
    chunks = []
    for entry in entries:
        count = int(entry["count"])
        chunks.append({**entry, "timeline_start": total})
        total += count
    manifest = {"format": "eclipse_video_run", "version": 1, "kind": kind,
                "fps": float(fps), "width": width, "height": height, "channels": channels,
                "dtype": dtype, "frame_count": total, "chunks": chunks, "audio": None}
    checkpoint = root / "checkpoint.json"
    if checkpoint.is_file():
        saved = read_json_object(checkpoint)
        manifest.update(checkpoint=checkpoint.name, total_parts=saved["total_parts"],
                        total_frames=saved["total_frames"],
                        status="complete" if len(chunks) == saved["total_parts"] else "partial")
    if audio is not None:
        waveform = audio["waveform"].detach().to(device="cpu", dtype=torch.float32).contiguous()
        # A run has one selected master soundtrack. It is saved once, before its
        # first manifest, and is independent of input/temp paths after restart.
        path = root / "soundtrack.npy"
        if not path.exists():
            _save_array(path, waveform.numpy())
        manifest["audio"] = {"file": path.name, "sample_rate": int(audio["sample_rate"])}
    for key in ("workflow", "prompt"):
        value = (metadata or {}).get(key)
        if isinstance(value, dict) and not (root / f"{key}.json").exists():
            if key == "prompt":
                # ComfyUI inserts execution-cache fingerprints into prompt nodes.
                # These can contain NaN (always rerun) and are not API inputs.
                value = {node_id: {k: v for k, v in node.items() if k != "is_changed"}
                         if isinstance(node, dict) else node for node_id, node in value.items()}
            write_json_object(root / f"{key}.json", value)
    write_json_object(root / MANIFEST, manifest)
    return str(root / MANIFEST)


def save_frame_run(timeline, audio=None, metadata=None):
    if timeline.storage != "persistent":
        return None
    root = Path(timeline.run_directory)
    entries = [{"file": Path(chunk.path).relative_to(root).as_posix(),
                "start": chunk.start, "count": chunk.count,
                **({"seed": str(chunk.seed)} if chunk.seed is not None else {})} for chunk in timeline.chunks]
    return save_run(root, kind="frames", fps=timeline.fps, width=timeline.width,
                    height=timeline.height, channels=timeline.channels, dtype=timeline.dtype,
                    entries=entries, audio=audio, metadata=metadata)


def manifest_path(path):
    import folder_paths

    p = Path(path.strip()).expanduser()
    if not p.is_absolute():
        p = Path(folder_paths.get_output_directory()) / p
    return p / MANIFEST if p.is_dir() else p


def _contained_file(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("Run file paths must be relative to the saved run folder.")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Saved run file is missing or outside its folder: {value}")
    return path


def _positive_int(value, label, allow_zero=False):
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise ValueError(f"Saved run {label} must be {'nonnegative' if allow_zero else 'positive'} integer.")
    return value


def load_video_run(path):
    from .frame_timeline import FrameChunk, FrameTimeline

    manifest_file = manifest_path(path)
    if not manifest_file.is_file():
        raise ValueError("Select a saved run.json or its folder. Loose frame chunks need an ordered manifest.")
    value = read_json_object(manifest_file)
    if (value.get("format") != "eclipse_video_run" or value.get("version") != 1
            or value.get("kind") not in ("frames", "clips")):
        raise ValueError("Unsupported saved video run format.")
    root = manifest_file.parent
    fps = value.get("fps")
    if type(fps) not in (int, float) or not math.isfinite(fps) or fps <= 0:
        raise ValueError("Saved run FPS must be positive and finite.")
    width = _positive_int(value.get("width"), "width")
    height = _positive_int(value.get("height"), "height")
    channels = value.get("channels")
    if channels not in (1, 3, 4):
        raise ValueError("Saved run has unsupported pixel channels.")
    expected_count = _positive_int(value.get("frame_count"), "frame count")
    entries = value.get("chunks")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Saved run must contain an ordered chunk list.")
    chunks, clips, total, size = [], [], 0, 0
    dtype = value.get("dtype")
    if value["kind"] == "frames" and dtype not in ("float16", "float32", "float64", "bfloat16"):
        raise ValueError("Saved run has unsupported pixel dtype.")
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("timeline_start") != total:
            raise ValueError("Saved run chunk positions are incomplete or out of order.")
        count = _positive_int(entry.get("count"), "chunk count")
        start = _positive_int(entry.get("start", 0), "chunk start", True)
        file = _contained_file(root, entry.get("file"))
        size += file.stat().st_size
        if value["kind"] == "frames":
            mapping = np.load(file, mmap_mode="r", allow_pickle=False)
            try:
                expected_dtype = np.dtype("uint16" if dtype == "bfloat16" else dtype)
                if (mapping.ndim != 4 or mapping.shape[1:] != (height, width, channels)
                        or mapping.dtype != expected_dtype or start + count > len(mapping)
                        or file.stat().st_size != mapping.offset + mapping.nbytes):
                    raise ValueError(f"Saved chunk shape, dtype or range differs from its manifest: {file.name}")
            finally:
                mapping._mmap.close()
            # The established chunk contract uses frames.npy within each folder.
            if file.name != "frames.npy":
                raise ValueError("Frame chunks must be named frames.npy.")
            seed = entry.get("seed")
            if seed is not None:
                if not isinstance(seed, str) or not seed.isascii() or not seed.isdecimal() or not 0 <= int(seed) < 2**64:
                    raise ValueError("Saved part seed must be an unsigned 64-bit decimal string.")
                seed = int(seed)
            chunks.append(FrameChunk(StoredDirectory(str(file.parent)), start, count, seed))
        else:
            from comfy_api.latest import InputImpl

            clip = InputImpl.VideoFromFile(str(file))
            if (start != 0 or clip.get_frame_count() != count
                    or tuple(clip.get_dimensions()) != (width, height)
                    or not math.isclose(float(clip.get_frame_rate()), fps, rel_tol=1e-6)):
                raise ValueError("Saved video clip differs from its recorded timing or dimensions.")
            clips.append(clip)
        total += count
    if total != expected_count:
        raise ValueError("Saved run frame count differs from its chunks.")
    audio = None
    if value.get("audio") is not None:
        item = value["audio"]
        if not isinstance(item, dict):
            raise ValueError("Saved soundtrack metadata must be an object.")
        rate = _positive_int(item.get("sample_rate"), "audio sample rate")
        file = _contained_file(root, item.get("file"))
        array = np.load(file, allow_pickle=False)
        if array.dtype != np.float32 or array.ndim != 3 or array.shape[0] != 1 or min(array.shape) < 1:
            raise ValueError("Saved soundtrack must contain one float32 AUDIO batch.")
        audio = {"waveform": torch.from_numpy(array), "sample_rate": rate}
        size += file.stat().st_size
    if chunks:
        source = FrameTimeline(tuple(chunks), height, width, channels, dtype, float(fps),
                               "persistent", str(root))
    else:
        from comfy_api.latest import InputImpl

        source = InputImpl.VideoFromList(clips, complete_audio=audio)
        source._eclipse_run_directory = str(root)
        source._eclipse_run_entries = tuple(entries)
    report = (f"{len(entries)} parts; {total} frames; {total / fps:.3f}s at {fps:g} FPS; "
              f"{width}×{height}; {size / 1024**3:.3f} GiB.\n{manifest_file}")
    return source, audio, float(fps), width, height, total, report


def memory_source(source):
    from .frame_timeline import FrameTimeline, MemoryFrameChunk

    if isinstance(source, FrameTimeline):
        chunks = []
        offset = 0
        for chunk in source.chunks:
            frames = torch.stack(list(source.slice(offset, chunk.count)))
            chunks.append(MemoryFrameChunk(frames, 0, chunk.count, chunk.seed))
            offset += chunk.count
        return FrameTimeline(tuple(chunks), source.height, source.width, source.channels,
                             source.dtype, source.fps, "memory")
    from .video_clip_append import MemoryClipVideo

    parts = [clip.get_components() for clip in source.videos]
    return MemoryClipVideo(tuple((part.images, part.audio) for part in parts),
                           float(parts[0].frame_rate), source.complete_audio)
