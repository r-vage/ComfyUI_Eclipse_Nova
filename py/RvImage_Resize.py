# One DOM resize editor with independently connected dimension overrides.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.resize_configuration import (
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    execute_configuration,
    validate_configuration,
)


class RvImage_Resize(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        template = io.MatchType.Template("image_or_mask", allowed_types=[io.Image, io.Mask])
        return io.Schema(
            node_id="Image Resize [Eclipse Nova]",
            display_name="Image Resize",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_TRANSFORMS.value,
            description="Resize images and masks with a compact editor. Connected non-None width and height override their respective target dimensions before divisor alignment and fitting.",
            is_input_list=True,
            inputs=[
                io.MatchType.Input("image", template=template, tooltip="Image or mask, as a batch or list."),
                io.String.Input("configuration", socketless=True,
                                default=json.dumps(default_configuration()),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec()}),
                io.Mask.Input("mask", optional=True, tooltip="Resize this mask together with the image."),
                io.Int.Input("width", force_input=True, optional=True, min=0, max=16384,
                             tooltip="Overrides the target width in any mode when non-None. 0 uses the source width. Fitting and divisor alignment still apply."),
                io.Int.Input("height", force_input=True, optional=True, min=0, max=16384,
                             tooltip="Overrides the target height in any mode when non-None. 0 uses the source height. Fitting and divisor alignment still apply."),
            ],
            outputs=[
                io.MatchType.Output(template=template, id="image", is_output_list=True),
                io.Mask.Output("mask", is_output_list=True),
                io.Int.Output("width"), io.Int.Output("height"),
            ],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, image, configuration, mask=None, width=None, height=None):
        return io.NodeOutput(*execute_configuration(image, configuration, mask, width, height))
