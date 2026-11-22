# ruff: noqa: N999 -- preserve the repository's role-based Legacy module names.
"""Original segmented H3 timeline planner."""
from comfy_api.latest import io

from ...core import CATEGORY
from ...core.minimax_h3_panels import MiniMaxPanel, panel_schema
from ...core.minimax_h3_segment_plan import PLAN_KIND


class RvVideo_MiniMaxH3SegmentedTimelinePanel(MiniMaxPanel):
    KIND = "segmented_timeline"

    @classmethod
    def define_schema(cls):
        return panel_schema(cls.KIND, [
            io.Audio.Input("audio", tooltip="Untouched master audio defines retained frames and the final mux."),
            io.Image.Input("image_batch", tooltip="Original timeline images. The transition frame belongs to its destination."),
            io.AudioEncoderOutput.Input("audio_encoder_output", optional=True, tooltip="Optional Wav2Vec activity features."),
            io.Audio.Input("conditioning_audio", optional=True, tooltip="Native-rate guide audio; use the same source in Plan Step."),
        ], [io.Custom(PLAN_KIND).Output("plan"), io.Int.Output("extension_task_count"), io.Int.Output("total_frames"),
            io.Int.Output("base_keep_frames"), io.String.Output("analysis_manifest"), io.String.Output("report")], category=CATEGORY.LEGACY)
