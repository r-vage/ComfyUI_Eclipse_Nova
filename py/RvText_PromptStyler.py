# Prompt Styler: one compact Jade editor, with the final public node name.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.styler_configuration import (
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    fingerprint,
    selected_template,
    style_prompts,
    validate_configuration,
)


class RvText_PromptStyler(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Prompt Styler [Eclipse Nova]",
            display_name="Prompt Styler",
            category=CATEGORY.MAIN.value + CATEGORY.TEXT.value,
            description="Apply CSV/JSON prompt styles with independent positive, negative and underscore controls. Style names survive library changes; index actions advance only on accepted queues.",
            inputs=[
                io.String.Input("text_positive", force_input=True,
                                tooltip="Base positive prompt, inserted at {prompt}."),
                io.String.Input("configuration", socketless=True,
                                default=json.dumps(default_configuration()),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec()}),
                io.String.Input("text_negative", default="", force_input=True, optional=True,
                                tooltip="Additional negative prompt, appended to the style's negative text."),
            ],
            outputs=[io.String.Output("text_positive"), io.String.Output("text_negative")],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            selected_template(validate_configuration(configuration), randomize=False)
        except (TypeError, ValueError, OSError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        return fingerprint(configuration)

    @classmethod
    def execute(cls, configuration, text_positive, text_negative=""):
        return io.NodeOutput(*style_prompts(configuration, text_positive, text_negative))
