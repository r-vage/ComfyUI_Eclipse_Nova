# Themed image selection panel, sharing the established pause/resume protocol.

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_review_configuration import (
    WIDGET_TYPE,
    default_configuration,
    validate_configuration,
)
from ..core.image_selection import select_images, selector_fingerprint


class RvImage_Selector(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Image Selector [Eclipse Nova]",
            display_name="Image Selector",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_SAVE_PREVIEW.value,
            description="Select images in order, then Confirm to continue the workflow. Shift+click selects a range; double-click opens a larger preview. Auto confirm passes all images without pausing for the current session.",
            is_input_list=True, is_output_node=True,
            inputs=[
                io.Image.Input("images", tooltip="Image batches or lists, including mixed sizes."),
                io.String.Input("configuration", socketless=True, default=default_configuration("selector"),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": {"kind": "selector"}}),
            ],
            outputs=[
                io.Image.Output("images", tooltip="Selected images in click order, resized to the first selection's dimensions."),
                io.Custom("LIST").Output("indices", tooltip="Selected zero-based image indices, in output order."),
            ],
            hidden=[io.Hidden.unique_id, io.Hidden.prompt, io.Hidden.extra_pnginfo],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, "selector")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **kwargs):
        config = validate_configuration(configuration, "selector")
        return selector_fingerprint(trigger=config["trigger"], auto_confirm=config["auto_confirm"])

    @classmethod
    def execute(cls, images, configuration):
        config = validate_configuration(configuration, "selector")
        return select_images(images, unique_id=cls.hidden.unique_id, prompt=cls.hidden.prompt,
                             extra_pnginfo=cls.hidden.extra_pnginfo, auto_confirm=config["auto_confirm"])
