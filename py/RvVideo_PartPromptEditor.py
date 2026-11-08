# Per-part text edits are consumed only when resuming a saved run.
import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.video_part_prompts import (
    EDITS_TYPE,
    WIDGET_TYPE,
    default_configuration,
    validate_configuration,
)


class RvVideo_PartPromptEditor(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Part Prompt Editor [Eclipse Nova]", display_name="Part Prompt Editor",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Read final part prompts from the connected Load Video Run, edit selected parts, and apply the replacements on Resume. Uses the same part numbers as Restart part. Timing, references, audio and retained media are unchanged; edits are saved in the new revision.",
            inputs=[io.String.Input("run_path", optional=True, force_input=True, lazy=True,
                                   tooltip="Connect Load Video Run's run_path directly or through Get/Set. Read selected run loads prompt text only; no models or media arrays."),
                    io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration()),
                                    extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": {}})],
            outputs=[io.Custom(EDITS_TYPE).Output("prompt_edits", tooltip="Connect to Video Loop Start's prompt_edits input. Used only on Resume. Set Restart part to the first changed completed part, or 0 to edit upcoming parts.")])

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def check_lazy_status(cls, **kwargs):
        # run_path identifies the picker to the frontend. The consumer validates
        # edits against its restored checkpoint; disabled edits never load media.
        return []

    @classmethod
    def execute(cls, configuration, run_path=None):
        config = validate_configuration(configuration)
        return io.NodeOutput(config)
