# Smart Sampler Settings with the Eclipse Nova DOM editor.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.sampler_configuration import (
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    settings_pipe,
    validate_configuration,
)


class RvSettings_SmartSamplerSettings(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Smart Sampler Settings [Eclipse Nova]",
            display_name="Smart Sampler Settings",
            category=CATEGORY.MAIN.value + CATEGORY.SETTINGS.value,
            description="Select the settings to include in a PIPE. Inactive settings keep their editor values but are omitted from the output. Allow IO inputs to override controls priority in IO Sampler Settings.",
            inputs=[io.String.Input("configuration", socketless=True,
                                    default=json.dumps(default_configuration("settings")),
                                    extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec("settings")})],
            outputs=[io.Custom("PIPE").Output("pipe")],
            is_output_node=True,
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, "settings")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        config = validate_configuration(configuration, "settings")
        return float("nan") if config.get("seed", {}).get("policy") == "random" else configuration

    @classmethod
    def execute(cls, configuration):
        return io.NodeOutput(settings_pipe(validate_configuration(configuration, "settings")))
