from comfy_api.latest import io

from ..core import CATEGORY
from ..core.prompt_review import (
    DEFAULT_CONFIGURATION,
    WIDGET_TYPE,
    outputs,
    prepare_review,
    review_prompts,
    validate_configuration,
)


class RvText_PromptReview(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Prompt Review [Eclipse Nova]", display_name="Prompt Review",
            category=CATEGORY.MAIN.value + CATEGORY.TEXT.value,
            description="Display and edit incoming prompts. Queue again to use edited text, with Pause on or off. Enable Pause to hold a changed run for review, then Continue the same run. Unchanged inputs reuse the completed review when continuing from a downstream stop. Edits apply only to the matching source prompts.",
            is_input_list=True, is_output_node=True,
            inputs=[
                io.String.Input("prompts", force_input=True, optional=True,
                                tooltip="One prompt or a list of prompts. List order and multiline text are preserved."),
                io.String.Input("first_prompt", force_input=True, optional=True,
                                tooltip="Optional separate first prompt, for example Scene Analysis to H3's first_part_prompt. Review it together with the remaining prompts."),
                io.String.Input("configuration", socketless=True, default=DEFAULT_CONFIGURATION,
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": {}}),
            ],
            outputs=[io.String.Output("prompts", is_output_list=True), io.String.Output("first_prompt")],
            hidden=[io.Hidden.unique_id, io.Hidden.extra_pnginfo, io.Hidden.dynprompt],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **kwargs):
        # Keep completed approvals cacheable across downstream selector queues.
        # V3 hidden UNIQUE_ID is not included by every ComfyUI cache version;
        # explicitly separate identical review nodes so each can be approved.
        return cls.hidden.unique_id if validate_configuration(configuration)["pause"] else False

    @classmethod
    def execute(cls, configuration, prompts=None, first_prompt=None):
        config = validate_configuration(configuration)
        packet = prepare_review(prompts, first_prompt, config)
        if config["pause"] and packet["texts"]:
            packet = review_prompts(packet, cls.hidden)
        else:
            packet["status"] = "edited" if packet["texts"] != packet["originals"] else "passed"
        return io.NodeOutput(*outputs(packet), ui={"prompt_review": [
            {key: packet[key] for key in ("source", "has_first", "originals", "texts", "status")}
        ]})
