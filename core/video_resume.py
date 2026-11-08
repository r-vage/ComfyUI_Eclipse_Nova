# Resume at a completed part boundary without mutating the original saved run.
import os
import shutil
from dataclasses import replace
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
                   allow_complete=False):
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
    if start > len(counts) or start > len(ranges):
        raise ValueError("Restart part is beyond the completed parts or the current plan.")
    if counts[:start] != [count for _, count in ranges[:start]]:
        raise ValueError("Saved part boundaries differ from the current plan. Restore the original cut timings before resuming.")
    if start == len(ranges):
        if allow_complete:
            return previous, start, 0, "Saved run is complete; no parts require generation."
        raise ValueError("This run is already complete. Use Load saved run, or choose a restart part to regenerate.")
    prefix = _prefix(previous, start, storage or VideoStorage())
    report = (f"Keep {start} completed parts ({sum(counts[:start])} frames). "
              f"Generate parts {start + 1}–{len(ranges)}. "
              "The original run is unchanged.")
    return prefix, start, len(ranges) - start, report
