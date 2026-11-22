"""Video-only H3 planning with independent image descriptions and source clips."""
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_helpers import flatten_images, unwrap_value
from ..core.minimax_h3_native_plan import add_source_boundaries
from ..core.scene_analysis import APPEARANCE_MODES, PLAN_TYPE

_CATEGORY = CATEGORY.MAIN.value + CATEGORY.MINIMAX.value


class RvVideo_H3ImageInputsV2(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3 Image Inputs_v2 [Eclipse Nova]", display_name="H3 Image Inputs_v2", category=_CATEGORY,
            is_input_list=True,
            inputs=[io.Boolean.Input("require_images", default=False,
                                     tooltip="Enable before image description to report missing images clearly."),
                    io.Image.Input("images", optional=True)],
            outputs=[io.Image.Output("images", is_output_list=True), io.Boolean.Output("has_images"),
                     io.Combo.Output("appearance_mode", options=list(APPEARANCE_MODES))])

    @classmethod
    def execute(cls, require_images=False, images=None):
        frames = flatten_images(images)
        if unwrap_value(require_images) and not frames:
            raise ValueError("Image description is enabled: load an image and enable the Images group.")
        return io.NodeOutput(frames, bool(frames), "exclude source appearance" if frames else "include source appearance")


class RvVideo_SceneSourceBoundariesV2(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Scene Source Boundaries_v2 [Eclipse Nova]", display_name="Scene Source Boundaries_v2",
            category=_CATEGORY,
            description="Keep every loaded clip boundary even when scene detection or cut limiting merges similar clips. Connect after Scene Cut Limit and before Scene Analysis Plan.",
            inputs=[io.Custom(PLAN_TYPE).Input("scene_plan"), io.Video.Input("video")],
            outputs=[io.Custom(PLAN_TYPE).Output("scene_plan")])

    @classmethod
    def execute(cls, scene_plan, video):
        return io.NodeOutput(add_source_boundaries(scene_plan, video))
