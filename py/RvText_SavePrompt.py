# Compact prompt saver with the same destination/format layout as Save Images.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_helpers import unwrap_value
from ..core.prompt_files_configuration import (
    SAVE_WIDGET,
    default_configuration,
    editor_spec,
    validate_configuration,
)
from ..core.prompt_saving import save_prompts


class RvText_SavePrompt(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Save Prompt [Eclipse Nova]", display_name="Save Prompt",
            category=CATEGORY.MAIN.value + CATEGORY.TEXT.value,
            description="Save TXT, CSV or JSON prompts with source-aware names, all five write modes and aligned batches. Pipe output_path and filename_prefix override the panel when present.",
            is_output_node=True, is_input_list=True,
            inputs=[io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration("save")),
                                    extra_dict={"widgetType": SAVE_WIDGET, "editorSpec": editor_spec("save")}),
                    io.String.Input("text", force_input=True, tooltip="Prompt text or an aligned list of captions."),
                    io.String.Input("filename_opt", optional=True, force_input=True,
                                    tooltip="Source filepath or aligned list. Commas separate filenames; multiple filenames require matching prompts."),
                    io.Custom("PIPE").Input("pipe_opt", optional=True,
                                            tooltip="Source file information takes priority over filename_opt. Dedicated output_path and filename_prefix override panel values; path remains source context.")],
            outputs=[io.String.Output("text", is_output_list=True)],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(unwrap_value(configuration), "save")
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, configuration, text, filename_opt=None, pipe_opt=None):
        options = validate_configuration(unwrap_value(configuration), "save")["options"]
        if not options.pop("save_to_disk"):
            return io.NodeOutput(text if isinstance(text, list) else [text])
        return save_prompts(text=text, filename_opt=filename_opt, pipe_opt=pipe_opt, **options)
