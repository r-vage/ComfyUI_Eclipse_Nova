# One DOM comparison interface in classic canvas and Nodes 2.0.

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_comparison import compare_images
from ..core.image_review_configuration import (
    WIDGET_TYPE,
    default_configuration,
    validate_configuration,
)


class RvImage_Comparer(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Image Comparer [Eclipse Nova]",
            display_name="Image Comparer",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_SAVE_PREVIEW.value,
            description="Compare images with a hover slider or hold-to-compare Click mode. Navigate paired batches; a shorter side reuses its first image. Choose which complete input side passes downstream.",
            is_input_list=True, is_output_node=True,
            inputs=[
                io.Image.Input("image_a", optional=True, tooltip="Original image or image batches/lists."),
                io.Image.Input("image_b", optional=True, tooltip="Result image or image batches/lists."),
                io.String.Input("configuration", socketless=True, default=default_configuration("comparer"),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": {"kind": "comparer"}}),
            ],
            outputs=[io.Image.Output("image", is_output_list=True,
                                     tooltip="Complete chosen side, unchanged; uses the other side if the chosen input is empty. Default: B.")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, "comparer")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, configuration, image_a=None, image_b=None):
        config = validate_configuration(configuration, "comparer")
        return compare_images(image_a, image_b, default_side=config["output"],
                              prompt=cls.hidden.prompt, extra_pnginfo=cls.hidden.extra_pnginfo)
