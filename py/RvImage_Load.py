# Image browser with optional metadata and the original animation batch contract.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_loader_configuration import (
    IMAGE_WIDGET,
    default_image,
    editor_spec,
    validate_image,
)
from ..core.image_loading import file_fingerprint, load_image, source_image_path


class RvImage_Load(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Load Image [Eclipse Nova]", display_name="Load Image",
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_LOADERS.value,
            description="Browse input/output images, upload or drop images, and optionally extract generation metadata. Animations remain a batch; the pipe contains the filename and full path.",
            inputs=[io.String.Input("configuration", socketless=True, default=json.dumps(default_image()),
                                    extra_dict={"widgetType": IMAGE_WIDGET, "editorSpec": editor_spec("image")})],
            outputs=[io.Image.Output("image"), io.Mask.Output("mask"), io.Custom("PIPE").Output("pipe")],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            source_image_path(validate_image(configuration))
        except (TypeError, ValueError, OSError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        return file_fingerprint(source_image_path(validate_image(configuration)))

    @classmethod
    def execute(cls, configuration):
        return io.NodeOutput(*load_image(validate_image(configuration)))
