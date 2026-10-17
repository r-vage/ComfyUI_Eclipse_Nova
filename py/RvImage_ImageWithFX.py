# Compact structured editor for image compositing and optional effects.
import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.fx_configuration import (
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    render_configuration,
    validate_configuration,
)


class RvImage_ImageWithFX(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Image with FX [Eclipse Nova]",
            display_name="Image with FX",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_FX.value,
            description="Composite a logo, signature or watermark with a compact FX editor. Glow and Shadow enable independent sections. The first source image and mask are applied to every background frame.",
            inputs=[
                io.Image.Input("background_image", tooltip="Background image or batch."),
                io.Image.Input("input_image", tooltip="Image to composite. Its alpha supplies the shape when no mask is connected."),
                io.String.Input("configuration", socketless=True,
                                default=json.dumps(default_configuration("image")),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec("image")}),
                io.Mask.Input("mask", optional=True, tooltip="Optional shape mask; the Image section controls inversion."),
            ],
            outputs=[io.Image.Output("image"), io.Mask.Output("mask")],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, "image")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, background_image, input_image, configuration, mask=None):
        return io.NodeOutput(*render_configuration(configuration, "image", background_image=background_image,
                                                    input_image=input_image, mask=mask))
