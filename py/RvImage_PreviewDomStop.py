# DOM image/mask preview with an optional stop and unchanged list passthrough.

import nodes
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.review_preview import (
    DEFAULT_CONFIGURATION,
    WIDGET_TYPE,
    image_preview,
    validate_configuration,
)


class RvImage_PreviewDomStop(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        template = io.MatchType.Template("image_or_mask", allowed_types=[io.Image, io.Mask])
        return io.Schema(
            node_id="Image Preview [Eclipse Nova]",
            display_name="Image Preview",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_SAVE_PREVIEW.value,
            description="Resizable image or grayscale mask preview with batch grids and navigation. Stop interrupts the current workflow after preparing the preview; disabled by default. The output follows the input type and passes original batches through unchanged.",
            is_input_list=True,
            is_output_node=True,
            inputs=[
                io.MatchType.Input("images", template=template, display_name="image | mask",
                                   tooltip="IMAGE [batch, height, width, channels] or MASK [batch, height, width], including lists and mixed frame sizes. Masks display black at 0 and white at 1."),
                io.String.Input("configuration", socketless=True, default=DEFAULT_CONFIGURATION,
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": {"kind": "image"}}),
            ],
            outputs=[io.MatchType.Output(template=template, id="IMAGE", display_name="image | mask",
                                         tooltip="Original images or masks, unchanged. The socket type follows the input.",
                                         is_output_list=True)],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, images, configuration):
        config = validate_configuration(configuration)
        ui = image_preview(images, cls.hidden.prompt, cls.hidden.extra_pnginfo)
        if config["stop"] and ui["images"]:
            nodes.interrupt_processing()
        return io.NodeOutput(images, ui=ui)
