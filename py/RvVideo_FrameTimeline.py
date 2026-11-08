# Append, trim and gate disk-backed frame timelines.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.frame_timeline import TIMELINE_TYPE, FrameTimeline, append_frames
from ..core.node_debug import debug_event, debug_node
from ..core.operation_panel import OperationPanel
from ..core.video_run import STORAGE_TYPE, save_frame_run

_LOG_PREFIX = "FrameTimeline"


class RvVideo_TimelineLoopGate(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Frame Timeline Loop Gate [Eclipse Nova]",
            display_name="Frame Timeline Loop Gate",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Block extension execution when there are no extensions. Use has_extensions with a lazy If/Else to choose loop output or the base timeline.",
            inputs=[io.Custom(TIMELINE_TYPE).Input("timeline"),
                    io.Int.Input("extensions", default=0, min=0, max=1000000)],
            outputs=[io.Custom(TIMELINE_TYPE).Output("loop_timeline"),
                     io.Boolean.Output("has_extensions")],
        )

    @classmethod
    @debug_node(_LOG_PREFIX)
    def execute(cls, timeline, extensions):
        from comfy_execution.graph_utils import ExecutionBlocker

        debug_event(_LOG_PREFIX, "Loop gate", extensions=extensions, enabled=extensions > 0)
        return io.NodeOutput(timeline if extensions > 0 else ExecutionBlocker(None), extensions > 0)


class RvVideo_DecodeAppendTimeline(OperationPanel, io.ComfyNode):
    PANEL_KIND = "timeline_append"

    @classmethod
    def define_schema(cls):
        schema = super().define_schema()
        added = {"storage", "soundtrack", "generation_seed"}
        schema.inputs = ([field for field in schema.inputs if field.id not in added | {"configuration"}]
                         + [field for field in schema.inputs if field.id in added]
                         + [field for field in schema.inputs if field.id == "configuration"])
        return schema

    @classmethod
    def operation_schema(cls):
        return io.Schema(
            node_id="Decode and Append Timeline [Eclipse Nova]",
            display_name="Decode and Append Timeline",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Native VAE decode and retain an exact frame range. Optional Video Run Storage chooses CPU RAM, temporary disk or persistent output. Existing connections default to temporary disk.",
            inputs=[io.Latent.Input("samples"), io.Vae.Input("vae"),
                    io.Int.Input("crop_start", default=0, min=0),
                    io.Int.Input("keep_frames", default=1, min=1, max=1000000),
                    io.Float.Input("fps", default=24, min=1, max=120),
                    io.Custom(TIMELINE_TYPE).Input("timeline", optional=True),
                    io.Custom(STORAGE_TYPE).Input("storage", optional=True,
                        tooltip="Connect Video Run Storage. RAM keeps exact frames in CPU memory; persistent disk writes a reloadable run after every completed part."),
                    io.Audio.Input("soundtrack", optional=True,
                        tooltip="Full selected soundtrack. Persistent runs save it once for reuse after restart."),
                    io.Int.Input("generation_seed", optional=True, force_input=True, min=0, max=2**64-1,
                        tooltip="Exact seed used by RandomNoise for this part. Saved in the run manifest for later review and resume.")],
            outputs=[io.Custom(TIMELINE_TYPE).Output("timeline"), io.String.Output("run_path")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
        )

    @classmethod
    @debug_node(_LOG_PREFIX)
    def execute_operation(cls, samples, vae, crop_start, keep_frames, fps, timeline=None,
                          storage=None, soundtrack=None, generation_seed=None):
        latent = samples["samples"]
        if latent.is_nested:
            latent = latent.unbind()[0]
        debug_event(_LOG_PREFIX, "VAE decode started", latent=latent)
        images = vae.decode(latent)
        debug_event(_LOG_PREFIX, "VAE decode finished", images=images)
        if images.ndim == 5:
            images = images.reshape(-1, *images.shape[-3:])
        if crop_start < 0 or keep_frames < 1 or crop_start + keep_frames > images.shape[0]:
            raise ValueError("Planned retained range exceeds the decoded scene.")
        result = append_frames(images[crop_start:crop_start + keep_frames], fps, timeline,
                               storage=storage, generation_seed=generation_seed)
        metadata = {"workflow": (getattr(cls.hidden, "extra_pnginfo", None) or {}).get("workflow"),
                    "prompt": getattr(cls.hidden, "prompt", None)} if result.storage == "persistent" else None
        path = save_frame_run(result, soundtrack, metadata)
        return io.NodeOutput(result, path or "")


class RvVideo_TrimTimeline(OperationPanel, io.ComfyNode):
    PANEL_KIND = "timeline_trim"

    @classmethod
    def operation_schema(cls):
        return io.Schema(
            node_id="Trim Frame Timeline [Eclipse Nova]",
            display_name="Trim Frame Timeline",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            inputs=[io.Custom(TIMELINE_TYPE).Input("timeline"),
                    io.Int.Input("start", default=0, min=0),
                    io.Int.Input("count", default=1, min=1, max=1000000)],
            outputs=[io.Custom(TIMELINE_TYPE).Output("timeline"),
                     io.Int.Output("width"), io.Int.Output("height"), io.Int.Output("count")],
        )

    @classmethod
    @debug_node(_LOG_PREFIX)
    def execute_operation(cls, timeline, start, count):
        if not isinstance(timeline, FrameTimeline):
            raise TypeError("Expected an Eclipse frame timeline.")
        result = timeline.slice(start, count)
        return io.NodeOutput(result, result.width, result.height, len(result))
