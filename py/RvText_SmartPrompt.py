# Smart Prompt: path-based file selections in one renderer-independent editor.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.smart_prompt import (
    MAX_SEED,
    WIDGET_TYPE,
    default_configuration,
    fingerprint,
    generate,
    selected_files,
    validate_configuration,
)


class RvText_SmartPrompt(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Smart Prompt [Eclipse Nova]",
            display_name="Smart Prompt",
            category=CATEGORY.MAIN.value + CATEGORY.TEXT.value,
            description="Build a prompt from your text files. Folder sections and file rows can be reordered; selections stay attached to their paths. Local seed ignores seed_input when enabled.",
            inputs=[
                io.String.Input("configuration", socketless=True,
                                default=json.dumps(default_configuration()),
                                extra_dict={"widgetType": WIDGET_TYPE}),
                io.Int.Input("seed_input", optional=True, force_input=True,
                             min=0, max=MAX_SEED,
                             tooltip="Used only when Local seed is disabled."),
            ],
            outputs=[io.String.Output("prompt")],
            is_output_node=True,
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            selected_files(validate_configuration(configuration))
        except (TypeError, ValueError, OSError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        return fingerprint(configuration)

    @classmethod
    def execute(cls, configuration, seed_input=None):
        prompt, seed = generate(configuration, seed_input)
        return io.NodeOutput(prompt, ui={"eclipse_prompt": [prompt], "eclipse_seed": [str(seed)]})
