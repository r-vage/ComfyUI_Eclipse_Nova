# Combined image finishing panel for classic canvas and Nodes 2.0.
import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_adjustments import execute_configuration
from ..core.image_adjustments_configuration import (
    WIDGET_TYPE,
    configuration_fingerprint,
    default_configuration,
    editor_spec,
    validate_configuration,
)


class RvImage_FilterAdjustmentsAdvanced(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Image Filter Adjustments Advanced [Eclipse Nova]",
            display_name="Image Filter Adjustments Advanced",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_FX.value,
            description="Soften, scale with or without a model, match reference colors, grade, sharpen and finish images. Sections follow processing order. Alpha is preserved separately from RGB effects.",
            is_input_list=True,
            inputs=[
                io.Image.Input("image", tooltip="Target image batch or list; passes through on bypass."),
                io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration()),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec()}),
                io.Image.Input("image_ref", optional=True, tooltip="Reference colors, used only when Color match is enabled with nonzero strength."),
                io.Float.Input("upscale_by", optional=True, force_input=True, min=0, max=16,
                               tooltip="Overrides the local target while Scale is enabled. Positive values scale from the original image; 0 keeps native model size (original size without a model). None uses the panel settings."),
            ],
            outputs=[io.Image.Output("image", is_output_list=True)],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration)
        except (ValueError, TypeError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **kwargs):
        return configuration_fingerprint(configuration)

    @classmethod
    def execute(cls, image, configuration, image_ref=None, upscale_by=None):
        return io.NodeOutput(execute_configuration(image, configuration, image_ref, upscale_by))
