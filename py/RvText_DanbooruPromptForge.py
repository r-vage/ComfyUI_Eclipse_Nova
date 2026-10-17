# Prompt Forge redesign: one structured text panel and an optional seed socket.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.forge_configuration import (
    MAX_SEED,
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    fingerprint,
    generate,
    validate_configuration,
)


class RvText_DanbooruPromptForge(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Danbooru Prompt Forge [Eclipse Nova]",
            display_name="Danbooru Prompt Forge",
            category=CATEGORY.MAIN.value + CATEGORY.DANBOORU.value,
            description="Choose an offline taglist with rating controls and collapsible text sections. Local seed ignores seed_input when enabled; disable it to use a connected seed.",
            inputs=[
                io.String.Input("configuration", socketless=True,
                                default=json.dumps(default_configuration()),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec()}),
                io.Int.Input("seed_input", optional=True, force_input=True,
                             min=0, max=MAX_SEED,
                             tooltip="Used only when Local seed is disabled."),
            ],
            outputs=[io.String.Output("text", tooltip="Prefix, required, custom and generated tags, with first-occurrence deduplication.")],
            is_output_node=True,
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        return fingerprint(configuration)

    @classmethod
    def execute(cls, configuration, seed_input=None):
        text, seed = generate(configuration, seed_input)
        return io.NodeOutput(text, ui={"eclipse_seed": [str(seed)], "eclipse_forge": [text]})
