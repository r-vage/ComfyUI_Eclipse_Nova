# Themed multiline editor with optional filtering, full text and per-line outputs.

import nodes
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.multiline_configuration import (
    DEFAULT_CONFIGURATION,
    MAX_TEXT_LENGTH,
    WIDGET_TYPE,
    text_outputs,
    validate_configuration,
)


class RvText_Multiline(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="String Multiline [Eclipse Nova]",
            display_name="String Multiline",
            category=CATEGORY.MAIN.value + CATEGORY.TEXT.value,
            description="Resizable text editor with string/list outputs and optional Filter, Preview and Stop. Filter removes editor patterns from input_string. Stop interrupts after a changed execution; queue again unchanged to continue. Wrap changes display only.",
            is_output_node=True,
            inputs=[
                io.String.Input("configuration", socketless=True, default=DEFAULT_CONFIGURATION,
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": {"maxTextLength": MAX_TEXT_LENGTH}}),
                io.String.Input("input_string", optional=True, force_input=True,
                                tooltip="Filter off: optional prefix, prepended verbatim to string and trimmed before each list item. Filter on: source prompt to filter using the patterns in the editor."),
            ],
            outputs=[io.String.Output("string"), io.String.Output("string_list", is_output_list=True)],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, configuration, input_string=None):
        config = validate_configuration(configuration)
        text, lines = text_outputs(config, input_string)
        ui = {"eclipse_multiline": [{"text": text}]} if config.get("preview", False) else {}
        if config.get("stop", False):
            # Normal ComfyUI caching lets an unchanged re-queue continue.
            nodes.interrupt_processing()
        return io.NodeOutput(text, lines, ui=ui)
