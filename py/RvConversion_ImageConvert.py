# Structured color conversion with the same ordered tensor operations.
import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_conversion import convert_images
from ..core.media_tool_configuration import (
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    validate_configuration,
)


class RvConversion_ImageConvert(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Image Convert [Eclipse Nova]", display_name="Image Convert",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_TRANSFORMS.value,
            description="Composite alpha onto a chosen color, convert to RGB or grayscale, then apply an optional style.",
            inputs=[io.Image.Input("images"),
                    io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration("convert")),
                                    extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec("convert")})],
            outputs=[io.Image.Output("images")],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, "convert")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, images, configuration):
        config = validate_configuration(configuration, "convert")
        return io.NodeOutput(convert_images(images, **config["parameters"]))
