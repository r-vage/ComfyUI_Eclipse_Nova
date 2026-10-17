# Unified dimensions for image/video workflows, without allocating a latent.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.resolution import (
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    resolution_pipe,
    validate_configuration,
)


class RvSettings_ResolutionPipe(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Resolution Pipe [Eclipse Nova]",
            display_name="Resolution Pipe",
            category=CATEGORY.MAIN.value + CATEGORY.SETTINGS.value,
            description="Image or video dimensions using aspect ratios, resolution presets, custom pixels or megapixels, and divisor alignment. Batch size is optional; disabled values are omitted from the PIPE.",
            inputs=[io.String.Input("configuration", socketless=True,
                                    default=json.dumps(default_configuration()),
                                    extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec()})],
            outputs=[io.Custom("PIPE").Output("pipe", tooltip="Width and height, plus batch_size when enabled.")],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, configuration):
        return io.NodeOutput(resolution_pipe(validate_configuration(configuration)))
