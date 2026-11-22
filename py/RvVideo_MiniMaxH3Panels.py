"""Conditioning and step nodes for segmented H3 rendering."""
from comfy_api.latest import io

from ..core.frame_timeline import TIMELINE_TYPE
from ..core.minimax_h3_panels import MiniMaxPanel, panel_schema
from ..core.minimax_h3_segment_plan import PLAN_KIND


class RvVideo_MiniMaxH3SegmentedStepPanel(MiniMaxPanel):
    KIND = "segmented_step"

    @classmethod
    def define_schema(cls):
        return panel_schema(cls.KIND, [
            io.Custom(PLAN_KIND).Input("plan"), io.Audio.Input("conditioning_audio", tooltip="Exactly the guide audio used by the planner."),
            io.Image.Input("image_batch"), io.Image.Input("previous_frames", optional=True),
            io.Custom(TIMELINE_TYPE).Input("timeline", optional=True, tooltip="Stored retained frames. Connect this or previous_frames; only requested continuity is read."),
        ], [io.Audio.Output("audio_slice"), io.Image.Output("continuity_clip"), io.Boolean.Output("has_continuity"),
            io.Image.Output("source_image"), io.Boolean.Output("has_start_guide"), io.Int.Output("start_guide_frame_index"),
            io.Image.Output("last_image"), io.Boolean.Output("has_last_image"), io.Int.Output("endpoint_frame_index"),
            io.Int.Output("render_frames"), io.Int.Output("crop_start_frames"), io.Int.Output("keep_frames"),
            io.Int.Output("prompt_index"), io.String.Output("conditioning_family"), io.String.Output("ref_image_size")])


class RvVideo_MiniMaxH3SegmentedConditioningPanel(MiniMaxPanel):
    KIND = "segmented_conditioning"

    @classmethod
    def define_schema(cls):
        schema = panel_schema(cls.KIND, [
            io.Clip.Input("clip"), io.Vae.Input("vae"), io.Image.Input("source_image"), io.Image.Input("last_image", optional=True),
            io.Custom(PLAN_KIND).Input("segment_plan", optional=True, tooltip="Connect with task_index to apply planned camera-cut directions."),
            io.Int.Input("task_index", optional=True, force_input=True, min=0, max=65535,
                         tooltip="Current plan task; requires segment_plan. Separate from the prompt owner."),
        ], [io.Conditioning.Output("positive")])
        schema.description = ("Global prompts apply throughout. Optional first_part_prompt describes the opening part; "
                              "planned cut instructions describe subsequent parts. The first part's pose is never appended to later parts.")
        schema.inputs.insert(-1, io.String.Input("first_part_prompt", optional=True, force_input=True,
                             tooltip="Specific framing, movement or expression for the first part only. Leave disconnected for global performance alone."))
        return schema
