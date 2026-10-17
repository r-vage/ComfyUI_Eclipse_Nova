# Structured Save Images panel and list-aware saving engine.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_helpers import unwrap_value
from ..core.image_saving import ImageSaver
from ..core.save_images_configuration import (
    FIELDS,
    WIDGET_TYPE,
    default_configuration,
    validate_configuration,
)


class RvImage_Save(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Save Images [Eclipse Nova]",
            display_name="Save Images",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_SAVE_PREVIEW.value,
            description="Save images with compact output, format and metadata sections. Pipe output_path (or path) and filename_prefix override local values when present.",
            is_output_node=True,
            is_input_list=True,
            inputs=[
                io.String.Input("configuration", socketless=True,
                                default=json.dumps(default_configuration()),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": {"fields": FIELDS}}),
                io.Image.Input("images", optional=True),
                io.Custom("PIPE").Input("pipe_opt", optional=True,
                                        tooltip="Generation data, optional images, and output_path/path or filename_prefix overrides. Missing/None values use the local settings."),
            ],
            outputs=[io.Image.Output("images", is_output_list=True), io.String.Output("files", is_output_list=True)],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(unwrap_value(configuration))
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, configuration, images=None, pipe_opt=None):
        options = validate_configuration(unwrap_value(configuration))["options"]
        result = ImageSaver(cls.hidden).execute(images=images, pipe_opt=pipe_opt, **options)
        # The preview-only engine also returns temporary files when its display
        # switch is off. Keep those out of native and exposed-subgraph previews.
        if not options["show_previews"]:
            result.ui["images"] = []
        return result
