# Compact typography and FX editor with a separate connected-text override.
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


class RvImage_TextImageWithFX(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Text Image with FX [Eclipse Nova]",
            display_name="Text Image with FX",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_FX.value,
            description="Render text with compact typography, placement, Stroke, Glow and Shadow sections. Background batches are supported; without a background the canvas fits the text and effects.",
            inputs=[
                io.String.Input("configuration", socketless=True,
                                default=json.dumps(default_configuration("text")),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec("text")}),
                io.Image.Input("background_image", optional=True, tooltip="Optional background image or batch. Without it, the canvas fits the text and effects."),
                io.String.Input("text_input", optional=True, force_input=True,
                                tooltip="When non-None, overrides the panel text. An empty string intentionally renders no text."),
            ],
            outputs=[io.Image.Output("image"), io.Mask.Output("mask")],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, "text")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, configuration, background_image=None, text_input=None):
        return io.NodeOutput(*render_configuration(configuration, "text", background_image=background_image,
                                                    text_input=text_input))
