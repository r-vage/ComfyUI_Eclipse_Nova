# Wildcard text/list editor with a result preview and exact local/input seeds.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.wildcard_configuration import (
    MAX_SEED,
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    fingerprint,
    generate,
    validate_configuration,
)


def _items(value):
    return value if isinstance(value, list) else [value]


class RvText_WildcardProcessorList(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Wildcard Processor [Eclipse Nova]",
            display_name="Wildcard Processor",
            category=CATEGORY.MAIN.value + CATEGORY.TEXT.value,
            description="Expand wildcard prompts with a live Result preview, or edit Result in Fixed mode. Returns full text and a list of non-empty lines, preserving spacing. Blank text supplies one empty list item.",
            inputs=[
                io.String.Input("configuration", socketless=True,
                                default=json.dumps(default_configuration()),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec()}),
                io.String.Input("wildcard_text", optional=True, force_input=True,
                                tooltip="Overrides Prompt in Populate mode, including an empty string. Fixed mode uses Result."),
                io.String.Input("substitutions", optional=True, force_input=True,
                                tooltip='Quoted assignments as text or a string list, separated by commas or line breaks. All entries are combined: S1:"a character", S2:"blue shirt". Use {{S1}} and {{S2}} in Prompt; applied before expansion in Populate mode.'),
                io.Int.Input("seed_input", optional=True, force_input=True, min=0, max=MAX_SEED,
                             tooltip="Used in Populate mode only when Local seed is disabled."),
            ],
            outputs=[io.String.Output("string", is_output_list=True), io.String.Output("list", is_output_list=True)],
            is_output_node=True, is_input_list=True,
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            for raw in _items(configuration) or [None]:
                validate_configuration(raw)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        return [fingerprint(raw) for raw in _items(configuration) or [None]]

    @classmethod
    def execute(cls, configuration, wildcard_text=None, substitutions=None, seed_input=None):
        configurations = _items(configuration) or [None]
        prompts = _items(wildcard_text) or [""]
        seeds = _items(seed_input) or [None]
        texts, lines, previews = [], [], []
        # Only substitutions are collected. Other input lists retain ComfyUI's
        # normal mapping: repeat the final value of each shorter input list.
        for index in range(max(len(configurations), len(prompts), len(seeds))):
            text, prompt_lines, seed = generate(
                configurations[min(index, len(configurations) - 1)],
                prompts[min(index, len(prompts) - 1)], substitutions,
                seeds[min(index, len(seeds) - 1)],
            )
            texts.append(text)
            lines.extend(prompt_lines)
            previews.append({"text": text, "seed": str(seed) if seed is not None else None})
        return io.NodeOutput(texts, lines, ui={"eclipse_wildcard": previews})
