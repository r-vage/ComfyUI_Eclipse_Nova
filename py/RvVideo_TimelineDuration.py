"""Share the duration choice between reference loading and render planning."""
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.video_reference_range import DURATIONS, RANGE_TYPE


class RvVideo_TimelineDuration(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Video Timeline Duration [Eclipse Nova]", display_name="Video Timeline Duration",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Select the same reference footage for scene analysis, embedded audio and render planning.",
            inputs=[io.Combo.Input("duration_source", options=list(DURATIONS)),
                    io.Float.Input("seconds", default=5, min=-1, max=86400, step=0.1,
                                   tooltip="Seconds per clip or across the playlist. Use −1 to keep the entire reference.")],
            outputs=[io.Combo.Output("duration_source", options=list(DURATIONS)), io.Float.Output("seconds"),
                     io.Custom(RANGE_TYPE).Output("reference_range", tooltip="Connect to Load Video, before detecting cuts.")],
        )

    @classmethod
    def execute(cls, duration_source, seconds):
        return io.NodeOutput(duration_source, seconds, {"duration_source": duration_source, "seconds": seconds})
