# Manual image slots feeding the image timeline renderer through a PIPE.
import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_blending import BLEND_MODES, BLEND_TOOLTIPS
from ..core.image_timeline_loader import (
    WIDGET_TYPE,
    default_configuration,
    fingerprint,
    load_images,
    validate_configuration,
)


class RvImage_LoadImageTimeline(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Load Image Timeline [Eclipse Nova]", display_name="Load Image Timeline",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_LOADERS.value,
            is_output_node=True,
            description="Add and reorder still images manually. Each slot has crop alignment and a blend into the next image. One selected image can supply sampler, prompts and seed metadata. Feed the PIPE to Image Timeline Video, adding audio and shared settings with IO Image Timeline. Optional width/height inputs override the corresponding local canvas values. Update previews resolves connected dimensions once for all images; without connections it refreshes locally.",
            inputs=[io.Int.Input("width", optional=True, force_input=True, min=0, max=8192,
                                 tooltip="Overrides local width when non-None. Zero derives width from the first enabled image and the height. Leave disconnected to use local width without running upstream nodes for previews."),
                    io.Int.Input("height", optional=True, force_input=True, min=0, max=8192,
                                 tooltip="Overrides local height when non-None. Zero derives height from the first enabled image and the width. Leave disconnected to use local height without running upstream nodes for previews."),
                    io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration()),
                                    extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": {
                                        "blend_modes": ["inherit", "cut", *BLEND_MODES], "blend_tooltips": BLEND_TOOLTIPS}})],
            outputs=[io.Custom("PIPE").Output("pipe", tooltip="Original images and per-slot settings for Image Timeline Video."),
                     io.Image.Output("images", is_output_list=True,
                                     tooltip="One batch of enabled images at the resolved canvas size, with per-slot fit/crop and no blending. Inherited fit uses Pad here. Alpha is preserved; RGB images become opaque when mixed with RGBA."),
                     io.String.Output("report")],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            config = validate_configuration(configuration)
            if not any(row["enabled"] and row["file"] is not None for row in config["images"]):
                return "Add and enable at least one image slot."
        except (ValueError, TypeError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        return fingerprint(configuration)

    @classmethod
    def execute(cls, configuration, width=None, height=None):
        output, images, report = load_images(configuration, width, height)
        return io.NodeOutput(output, images, report,
                             ui={"eclipse_image_timeline": [{"width": output["width"], "height": output["height"],
                                                            "input_dimensions": {"width": width, "height": height}, "report": report}]})
