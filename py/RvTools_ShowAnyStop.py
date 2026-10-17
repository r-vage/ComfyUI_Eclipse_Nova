# DOM text preview with an optional workflow stop and unchanged list passthrough.

import nodes
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.review_preview import (
    DEFAULT_CONFIGURATION,
    WIDGET_TYPE,
    format_value,
    validate_configuration,
)


class RvTools_ShowAnyStop(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        template = io.MatchType.Template("any_type")
        return io.Schema(
            node_id="Show Any Stop [Eclipse Nova]",
            display_name="Show Any Stop",
            category=CATEGORY.MAIN.value + CATEGORY.TOOLS.value,
            description="Display any input as text and pass it through unchanged. Stop interrupts the current workflow after displaying the result; disabled by default.",
            is_input_list=True,
            is_output_node=True,
            inputs=[
                io.MatchType.Input("anything", template=template, optional=True),
                io.String.Input("configuration", socketless=True, default=DEFAULT_CONFIGURATION,
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": {"kind": "text"}}),
            ],
            outputs=[io.MatchType.Output(template, id="output", is_output_list=True)],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, configuration, anything=None):
        config = validate_configuration(configuration)
        values = list(anything) if anything is not None else []
        ui = {"text": [format_value(value) for value in values]}
        if config["stop"]:
            nodes.interrupt_processing()
        return io.NodeOutput(values, ui=ui)
