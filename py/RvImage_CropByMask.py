# Compact mask-framing panel with optional connected target dimensions.
import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_crop_by_mask import crop_by_mask
from ..core.media_tool_configuration import (
    WIDGET_TYPE,
    crop_parameters,
    default_configuration,
    editor_spec,
    validate_configuration,
)


class RvImage_CropByMask(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Image Crop by Mask [Eclipse Nova]", display_name="Image Crop by Mask",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_TRANSFORMS.value,
            description="Frame the mask at the target size. Zoom below 1 includes context; above 1 crops closer. Outside-source pixels stay black and masked for inpainting.",
            inputs=[io.Image.Input("image"), io.Mask.Input("mask"),
                    io.Int.Input("target_width", optional=True, force_input=True, min=64, max=16384,
                                 tooltip="Connected non-None width overrides the panel."),
                    io.Int.Input("target_height", optional=True, force_input=True, min=64, max=16384,
                                 tooltip="Connected non-None height overrides the panel."),
                    io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration("crop")),
                                    extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec("crop")})],
            outputs=[io.Image.Output("image", is_output_list=True), io.Mask.Output("mask", is_output_list=True)],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, "crop")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, image, mask, configuration, target_width=None, target_height=None):
        config = validate_configuration(configuration, "crop")
        return io.NodeOutput(*crop_by_mask(image, mask, **crop_parameters(config, target_width, target_height)))
