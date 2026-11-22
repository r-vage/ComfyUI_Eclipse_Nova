# ruff: noqa: N999 -- preserve the repository's role-based Legacy module names.
# Eclipse adapter for the original extension-only WAN step contract.
from comfy_api.latest import io

from ...core import CATEGORY
from ...core.frame_timeline import TIMELINE_TYPE
from ...core.operation_panel import OperationPanel
from ...core.wan_timeline import WAN_KIND, resolve_extension


class RvVideo_WanLipSyncPlanStep(OperationPanel, io.ComfyNode):
    PANEL_KIND = "wan_step"

    @classmethod
    def operation_schema(cls):
        return io.Schema(
            node_id="WAN LipSync Plan Step [Eclipse Nova]",
            display_name="WAN LipSync Plan Step",
            description=(
                "Selects one frame-exact InfiniteTalk task and validates the "
                "accumulated timeline before sampling."
            ),
            category=CATEGORY.MAIN.value + CATEGORY.LEGACY.value,
            inputs=[
                io.Custom(WAN_KIND).Input("plan"),
                io.Int.Input("loop_index", default=0, min=0, max=65535, step=1),
                io.Image.Input("image_batch"),
                io.MatchType.Input("previous_frames", io.MatchType.Template("history", allowed_types=[io.Image, io.Custom(TIMELINE_TYPE)])),
                io.Combo.Input(
                    "blend_mode",
                    options=["linear", "pyramid"],
                    default="linear",
                ),
            ],
            outputs=[
                io.Image.Output("start_image"),
                io.Image.Output("previous_frames"),
                io.Int.Output("keep_frames"),
                io.Int.Output("trim_image", tooltip="Decoded crop start, including motion context and hidden warmup. Use instead of InfiniteTalk trim_image."),
                io.Int.Output("audio_start", tooltip="Absolute audio frame for WAN LipSync Conditioning; connect together with previous_frames."),
            ],
        )

    @classmethod
    def execute_operation(cls, plan, loop_index, image_batch, previous_frames, blend_mode):
        return io.NodeOutput(*resolve_extension(plan, loop_index, image_batch, previous_frames, blend_mode))
