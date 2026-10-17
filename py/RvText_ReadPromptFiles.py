# DOM panel reader with server-side, node-local iteration.

import json

from comfy_api.latest import io
from comfy_execution.graph_utils import ExecutionBlocker

from ..core import CATEGORY
from ..core.prompt_files_configuration import (
    READ_WIDGET,
    default_configuration,
    editor_spec,
    validate_configuration,
)
from ..core.prompt_reading import file_signature, read_prompt


class RvText_ReadPromptFiles(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Read Prompt Files [Eclipse Nova]", display_name="Read Prompt Files",
            category=CATEGORY.MAIN.value + CATEGORY.TEXT.value,
            description="Read non-empty lines from text files. Fixed, random, next, previous and shuffle selection advances on execution only. A connected seed freezes automatic selection until it changes.",
            inputs=[io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration("read")),
                                    extra_dict={"widgetType": READ_WIDGET, "editorSpec": editor_spec("read")}),
                    io.Int.Input("seed_input", optional=True, force_input=True,
                                 tooltip="Automatic selection advances only when this value changes. Fixed selection ignores it.")],
            outputs=[io.String.Output("prompt")],
            hidden=[io.Hidden.unique_id, io.Hidden.extra_pnginfo],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, "read")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        options = validate_configuration(configuration, "read")["options"]
        if options["advance"] != "fixed":
            return float("nan")
        return file_signature(options["file_paths"])

    @classmethod
    def execute(cls, configuration, seed_input=None):
        options = validate_configuration(configuration, "read")["options"]
        workflow = (cls.hidden.extra_pnginfo or {}).get("workflow", {})
        key = (workflow.get("id", "api"), str(cls.hidden.unique_id))
        prompt, info = read_prompt(options, key=key, seed=seed_input)
        return io.NodeOutput(ExecutionBlocker(None) if info["stopped"] else prompt,
                             ui={"eclipse_prompt_files": [info]})
