# Resume at a completed part boundary without mutating the original saved run.
import os
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from .frame_timeline import FrameChunk, FrameTimeline
from .image_helpers import unwrap_value
from .minimax_h3_clips import H3ClipPlan
from .minimax_h3_segment_plan import validate_segment_plan
from .video_run import (
    StoredDirectory,
    VideoStorage,
    create_run_directory,
    load_video_run,
    memory_source,
    save_frame_run,
    save_run,
)


@dataclass(frozen=True)
class PartReplacement:
    source: object
    part: int
    completed: int
    target: str | None = None
    revision: str | None = None


def part_seed(seed, index, increment=True):
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("Seed must be an unsigned 64-bit integer.")
    if type(index) is not int or index < 0:
        raise ValueError("Part index must be a nonnegative integer.")
    return (seed + index if increment else seed) % 2**64


def run_index(index, start_index):
    if any(type(value) is not int or value < 0 for value in (index, start_index)):
        raise ValueError("Loop index and start index must be nonnegative integers.")
    return start_index + index


def plan_ranges(plan):
    plan = unwrap_value(plan)
    if isinstance(plan, H3ClipPlan):
        ranges = [(clip.start, clip.keep) for clip in plan.clips]
        kind, fps = "clips", 24
    elif isinstance(plan, dict) and plan.get("kind") == "WAN_LIPSYNC_PLAN":
        from .wan_timeline import wan_parts

        if plan["fps"] != 25:
            raise ValueError("InfiniteTalk saved runs require 25 FPS.")
        ranges = [(task["start_frame"], task["keep_frames"]) for task in wan_parts(plan)]
        kind, fps = "frames", 25
    else:
        plan, tasks = validate_segment_plan(plan)
        ranges = [(task["output_start_frame"], task["keep_frames"]) for task in tasks]
        kind, fps = "frames", plan["fps"]
    cursor = 0
    for start, count in ranges:
        if start != cursor or type(count) is not int or count < 1:
            raise ValueError("Render plan must contain contiguous, nonempty parts.")
        cursor += count
    if not ranges:
        raise ValueError("Render plan contains no parts.")
    return kind, fps, ranges


def _copy_media(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _prefix(source, count, storage):
    from comfy_api.latest import InputImpl

    from .video_clip_append import MemoryClipVideo

    if not count:
        return None
    if isinstance(source, FrameTimeline):
        prefix = replace(source, chunks=source.chunks[:count])
        if storage.mode == "memory":
            return prefix if prefix.storage == "memory" else memory_source(prefix)
        if storage.mode == "temporary":
            # Borrow immutable saved chunks. New chunks use temporary ownership.
            return replace(prefix, storage="temporary", run_directory=None)
    elif isinstance(source, MemoryClipVideo):
        if storage.mode != "memory":
            raise ValueError("Load the saved run in Disk mode before resuming to disk.")
        return MemoryClipVideo(source.chunks[:count], source.fps, source.soundtrack)
    else:
        prefix = InputImpl.VideoFromList(source.videos[:count], complete_audio=source.complete_audio)
        if storage.mode == "memory":
            return memory_source(prefix)
        if storage.mode == "temporary":
            return prefix

    root = Path(create_run_directory(storage))
    try:
        if isinstance(source, FrameTimeline):
            chunks = []
            for index, chunk in enumerate(source.chunks[:count]):
                path = root / f"retained_{index:05d}" / "frames.npy"
                _copy_media(chunk.path, path)
                chunks.append(FrameChunk(StoredDirectory(str(path.parent)), chunk.start, chunk.count, chunk.seed))
            result = replace(source, chunks=tuple(chunks), storage="persistent", run_directory=str(root))
            audio = load_video_run(source.run_directory)[1] if source.run_directory else None
            save_frame_run(result, audio)
        else:
            entries = []
            videos = []
            source_root = Path(source._eclipse_run_directory)
            for index, entry in enumerate(source._eclipse_run_entries[:count]):
                original = source_root / entry["file"]
                file = f"retained_{index:05d}{original.suffix}"
                _copy_media(original, root / file)
                entries.append({**entry, "file": file})
                videos.append(InputImpl.VideoFromFile(str(root / file)))
            width, height = source.get_dimensions()
            save_run(root, kind="clips", fps=float(source.get_frame_rate()), width=width, height=height,
                     entries=entries, audio=source.complete_audio)
            result = InputImpl.VideoFromList(videos, complete_audio=source.complete_audio)
            result._eclipse_run_directory = str(root)
            result._eclipse_run_entries = tuple(entries)
        return result
    except BaseException:
        shutil.rmtree(root)
        raise


def prepare_resume(plan, resume=False, restart_part=0, previous=None, storage=None, width=0, height=0,
                   allow_complete=False, keep_following=False):
    from .video_clip_append import MemoryClipVideo

    kind, fps, ranges = plan_ranges(plan)
    if not resume:
        return None, 0, len(ranges), f"New run: {len(ranges)} parts."
    if previous is None:
        raise ValueError("Resume requires a source from Load Video Run. Select the run to continue.")
    if type(restart_part) is not int or restart_part < 0:
        raise ValueError("Restart part must be 0 (continue) or a one-based part number.")
    if isinstance(previous, FrameTimeline):
        source_kind, source_fps = "frames", previous.fps
        dimensions = (previous.width, previous.height)
        counts = [chunk.count for chunk in previous.chunks]
    elif isinstance(previous, MemoryClipVideo):
        source_kind, source_fps = "clips", previous.fps
        dimensions = previous.get_dimensions()
        counts = [len(images) for images, _ in previous.chunks]
    elif getattr(previous, "_eclipse_run_entries", None):
        source_kind, source_fps = "clips", float(previous.get_frame_rate())
        dimensions = previous.get_dimensions()
        counts = [entry["count"] for entry in previous._eclipse_run_entries]
    else:
        raise ValueError("Resume requires saved part boundaries; a finished MP4 alone cannot supply them.")
    if source_kind != kind or source_fps != fps:
        raise ValueError("Saved run mode/FPS differs from the current render plan. Restore the original mode and timings.")
    if (width and width != dimensions[0]) or (height and height != dimensions[1]):
        raise ValueError("Saved run dimensions differ from the current canvas. Restore its width and height before resuming.")
    start = len(counts) if restart_part == 0 else restart_part - 1
    if keep_following and (restart_part == 0 or start >= len(counts)):
        raise ValueError("Update selected run requires Restart part to select an already saved part, starting at 1.")
    if start > len(counts) or start > len(ranges):
        raise ValueError("Restart part is beyond the completed parts or the current plan.")
    checked = len(counts) if keep_following else start
    if counts[:checked] != [count for _, count in ranges[:checked]]:
        raise ValueError("Saved part boundaries differ from the current plan. Restore the original cut timings before resuming.")
    if start == len(ranges):
        if allow_complete:
            return previous, start, 0, "Saved run is complete; no parts require generation."
        raise ValueError("This run is already complete. Use Load saved run, or choose a restart part to regenerate.")
    prefix = _prefix(previous, start, storage or VideoStorage())
    report = (f"Keep {start} completed parts ({sum(counts[:start])} frames). "
              f"Generate parts {start + 1}–{len(ranges)}. "
              "The original run is unchanged.")
    if keep_following:
        report = (f"Replace part {restart_part} only; keep {start} earlier and "
                  f"{len(counts) - restart_part} later saved parts. The original run is unchanged.")
        if kind == "frames" and restart_part < len(counts) and (
            plan.get("kind") == "WAN_LIPSYNC_PLAN" or plan["tasks"][restart_part]["has_continuity"]
        ):
            report += " The following part used the old part's generated frames; review that join."
    return prefix, start, len(ranges) - start, report


def attach_saved_ending(source, replacement, storage, audio=None):
    from comfy_api.latest import InputImpl

    from .video_clip_append import MemoryClipVideo

    original, part = replacement.source, replacement.part
    if part == replacement.completed:
        return source
    if isinstance(source, FrameTimeline):
        tail = original.chunks[part:]
        if storage.mode != "persistent":
            if storage.mode == "memory" and original.storage != "memory":
                tail = memory_source(replace(original, chunks=tail)).chunks
            return replace(source, chunks=source.chunks + tail)
        root = Path(source.run_directory)
    elif isinstance(source, MemoryClipVideo):
        tail = (original.chunks[part:] if isinstance(original, MemoryClipVideo) else memory_source(
            InputImpl.VideoFromList(original.videos[part:], complete_audio=source.soundtrack)).chunks)
        return MemoryClipVideo(source.chunks + tail, source.fps, source.soundtrack)
    else:
        if storage.mode != "persistent":
            return InputImpl.VideoFromList([*source.videos, *original.videos[part:]], complete_audio=source.complete_audio)
        root = Path(source._eclipse_run_directory)

    # Stage immutable copies/links under the new revision. Publish its full
    # manifest only after every retained file is present; the source stays intact.
    staged = Path(tempfile.mkdtemp(prefix="RetainedEnding_", dir=root))
    try:
        if isinstance(source, FrameTimeline):
            chunks = []
            for index, chunk in enumerate(tail, part):
                path = staged / f"part_{index:05d}" / "frames.npy"
                _copy_media(chunk.path, path)
                chunks.append(FrameChunk(StoredDirectory(str(path.parent)), chunk.start, chunk.count, chunk.seed))
            result = replace(source, chunks=source.chunks + tuple(chunks))
            save_frame_run(result, audio)
        else:
            entries = list(source._eclipse_run_entries)
            videos = list(source.videos)
            original_root = Path(original._eclipse_run_directory)
            for index, entry in enumerate(original._eclipse_run_entries[part:], part):
                original_file = original_root / entry["file"]
                path = staged / f"part_{index:05d}{original_file.suffix}"
                _copy_media(original_file, path)
                entries.append({**entry, "file": path.relative_to(root).as_posix()})
                videos.append(InputImpl.VideoFromFile(str(path)))
            result = InputImpl.VideoFromList(videos, complete_audio=source.complete_audio)
            result._eclipse_run_directory = str(root)
            result._eclipse_run_entries = tuple(entries)
            width, height = result.get_dimensions()
            save_run(root, kind="clips", fps=float(result.get_frame_rate()), width=width, height=height,
                     entries=entries, audio=source.complete_audio)
        return result
    except BaseException:
        shutil.rmtree(staged)
        raise
