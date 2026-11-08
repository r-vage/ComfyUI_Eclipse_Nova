# Shared memory/disk controls and restart-independent saved-run loading.
from pathlib import Path

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.video_run import (
    NO_SAVED_RUNS,
    STORAGE_TYPE,
    VideoStorage,
    available_video_runs,
    load_video_run,
    manifest_path,
)


class RvVideo_RunStorage(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Video Run Storage [Eclipse Nova]", display_name="Video Run Storage",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="One storage control for frame timelines and native video clips. Disk off keeps decoded parts in CPU RAM. Disk on uses temporary files or persistent run folders. Preview/export still create video files in all modes.",
            inputs=[io.Combo.Input("run_mode", options=["New run", "Resume saved run", "Load saved run"], default="New run",
                        tooltip="New run prepares inputs and samples. Resume restores saved inputs and generates remaining/replacement parts. Load saved run exports existing media without planning or sampling."),
                    io.Boolean.Input("disk_timeline", default=True, label_on="Disk", label_off="RAM",
                        tooltip="Off: retain generated parts in CPU RAM, without frame/clip cache files. Requires more RAM, not more VRAM. On: retain parts on disk."),
                    io.Boolean.Input("keep_files", default=True, label_on="Keep in output", label_off="Temporary",
                        tooltip="Used with Disk enabled. On saves each completed part and a run.json manifest for reuse after restart. Off lets cached outputs own and clean temporary files. RAM ignores this option."),
                    io.String.Input("output_directory", default="video_runs",
                        tooltip="Persistent run parent folder, relative to ComfyUI output or an absolute path. Each new generation receives its own subfolder. Saved runs remain until you explicitly remove their folders.")],
            outputs=[io.Custom(STORAGE_TYPE).Output("storage"), io.Boolean.Output("generate", tooltip="True for New and Resume; select generated versus loaded final output."),
                     io.Boolean.Output("prepare", tooltip="True only for New run. Gate independent analysis, source and planning previews/reports with this output so resume does not recompute them.")])

    @classmethod
    def execute(cls, disk_timeline=True, keep_files=True, output_directory="video_runs", run_mode="New run"):
        mode = "memory" if not disk_timeline else "persistent" if keep_files else "temporary"
        return io.NodeOutput(VideoStorage(mode, output_directory, run_mode), run_mode != "Load saved run", run_mode == "New run")


class RvVideo_LoadRun(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        runs = available_video_runs()
        return io.Schema(
            node_id="Load Video Run [Eclipse Nova]", display_name="Load Video Run",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Reload a completed or partially completed saved run without models, reference analysis or sampling. Uses relative paths so the entire run folder can move. Original files are never owned or deleted by this loader.",
            inputs=[io.Combo.Input("saved_run", options=runs, default=runs[0],
                        tooltip="Select a saved run under ComfyUI output, including partially completed runs. Refresh runs after generating or moving a run; the current selection is preserved. Keep the whole run folder together when moving it."),
                    io.Custom(STORAGE_TYPE).Input("storage", optional=True,
                        tooltip="Optional shared storage control. RAM loads the saved parts into memory; Disk streams the existing files. Loading never creates another persistent copy.")],
            outputs=[io.AnyType.Output("source", tooltip="Exact frame timeline for lip-sync runs or VIDEO for native clips. Connect to Preview, captions or Save Video."),
                     io.Audio.Output("audio", tooltip="Saved master soundtrack. Native runs without an override retain their generated audio inside VIDEO."),
                     io.Float.Output("fps"), io.Int.Output("width"), io.Int.Output("height"),
                     io.Int.Output("frame_count"), io.String.Output("report", tooltip="Run folder, completed part count, duration and stored size."),
                     io.String.Output("run_path", tooltip="Connect to Video Loop Start for resolved checkpoint recovery. This is an output, not a second run selector."),
                     io.Custom("PIPE").Output("caption_context", tooltip="Saved full recording and excerpt start for IO Lyric Captions. Media-only older runs use their soundtrack from zero.")])

    @classmethod
    def validate_inputs(cls, saved_run):
        # ComfyUI validates inactive lazy branches too. Check availability only
        # when this loader executes; keep validation of other inputs intact.
        return True if isinstance(saved_run, str) else "Select a saved run from the dropdown."

    @classmethod
    def fingerprint_inputs(cls, saved_run, **kwargs):
        path = manifest_path(saved_run)
        stat = path.stat() if path.is_file() else None
        return (str(path), stat.st_mtime_ns, stat.st_size) if stat else str(path)

    @classmethod
    def execute(cls, saved_run, storage=None):
        if not saved_run or saved_run == NO_SAVED_RUNS:
            raise ValueError("No saved runs found. Generate with Disk and Keep files enabled under ComfyUI output, then click Refresh runs.")
        if saved_run not in available_video_runs():
            raise ValueError(f"Saved run '{saved_run}' is not available on this system. Click Refresh runs and select a local run, or switch the workflow to New run.")
        values = list(load_video_run(saved_run))
        from ..core.video_checkpoint import load_caption_context

        captions = load_caption_context(saved_run, values[1])
        if storage is not None and storage.mode == "memory":
            from ..core.video_run import memory_source

            values[0] = memory_source(values[0])
        return io.NodeOutput(*values, str(manifest_path(saved_run)), captions)


class RvVideo_RunGate(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Video Run Gate [Eclipse Nova]", display_name="Video Run Gate",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Skip an independent output and its dependencies while disabled. Use prepare for fresh source/analysis/planning outputs, generate for new or resumed rendering, or Video Loop Start's render output for per-part previews.",
            inputs=[io.AnyType.Input("value", optional=True, lazy=True, tooltip="Source feeding a preview, report or save node. Its upstream nodes are skipped when generate is false. A muted or absent optional source passes None while enabled."),
                    io.Boolean.Input("generate", default=True, tooltip="Connect Storage's prepare (new only), generate (new/resume), or Video Loop Start's render (an iteration is needed). False blocks this branch without requesting its source.")],
            outputs=[io.AnyType.Output("value", tooltip="Unchanged source while enabled, otherwise an execution blocker.")])

    @classmethod
    def check_lazy_status(cls, generate=True, **kwargs):
        return ["value"] if generate and "value" in kwargs and kwargs["value"] is None else []

    @classmethod
    def execute(cls, generate=True, value=None):
        from comfy_execution.graph_utils import ExecutionBlocker

        return io.NodeOutput(value if generate else ExecutionBlocker(None))


class RvVideo_RunInfo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Video Run Info [Eclipse Nova]", display_name="Video Run Info",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Read dimensions and timing from the actual selected run, independently of generation settings. Report each retained part's frame range for review and future edits.",
            inputs=[io.AnyType.Input("source", tooltip="Selected generated or loaded frame timeline/VIDEO. Reads metadata without decoding the full video.")],
            outputs=[io.Float.Output("fps"), io.Int.Output("width"), io.Int.Output("height"),
                     io.Int.Output("frame_count"), io.Float.Output("duration", tooltip="Video frame count divided by FPS, in seconds."),
                     io.String.Output("report", tooltip="Size and zero-based retained-part ranges, with each end excluded. A long scene can contain multiple render parts.")])

    @classmethod
    def execute(cls, source):
        from ..core.frame_timeline import FrameTimeline, MemoryFrameChunk
        from ..core.video_clip_append import MemoryClipVideo

        size = None
        if isinstance(source, FrameTimeline):
            fps, width, height, count = source.fps, source.width, source.height, len(source)
            parts = [c.count for c in source.chunks]
            run = source.run_directory
            size = sum(c.pixels.numel() * c.pixels.element_size() if isinstance(c, MemoryFrameChunk)
                       else Path(c.path).stat().st_size for c in source.chunks)
        else:
            fps = float(source.get_frame_rate())
            width, height = source.get_dimensions()
            count = source.get_frame_count()
            entries = getattr(source, "_eclipse_run_entries", ())
            parts = ([len(images) for images, _ in source.chunks] if isinstance(source, MemoryClipVideo)
                     else [e["count"] for e in entries] or [count])
            run = getattr(source, "_eclipse_run_directory", None)
            if isinstance(source, MemoryClipVideo):
                size = sum(images.numel() * images.element_size() for images, _ in source.chunks)
            elif run:
                size = sum((Path(run) / e["file"]).stat().st_size for e in entries)
        lines = [f"{count} frames; {count / fps:.3f}s at {fps:g} FPS; {width}×{height}."]
        if size is not None:
            lines.append(f"Video parts: {size / 1024**3:.3f} GiB (soundtrack and previews excluded).")
        if run:
            lines.append(f"Saved run: {run}/run.json")
        start = 0
        for index, length in enumerate(parts, 1):
            lines.append(f"Part {index}: frames [{start}, {start + length}), {start / fps:.3f}–{(start + length) / fps:.3f}s")
            start += length
        return io.NodeOutput(fps, width, height, count, count / fps, "\n".join(lines))
