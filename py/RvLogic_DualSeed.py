# Independent Image/Prompt seeds with a shared range and paired history.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.common import get_workflow_node
from ..core.dual_seed_configuration import (
    WIDGET_TYPE,
    default_configuration,
    resolve_configuration,
    validate_configuration,
)


class RvLogic_DualSeed(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Dual Seed_v2 [Eclipse Nova]",
            display_name="Dual Seed_v2",
            category=CATEGORY.MAIN.value + CATEGORY.PRIMITIVE.value,
            description="Independent Image and Prompt seeds with a shared 64-bit toggle and the last 50 seed pairs in Results.",
            inputs=[io.String.Input("configuration", socketless=True,
                                    default=json.dumps(default_configuration()),
                                    extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": {}})],
            outputs=[io.Int.Output("image"), io.Int.Output("prompt")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo, io.Hidden.unique_id],
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
        config = validate_configuration(configuration)
        return float("nan") if any(seed["policy"] == "random" for seed in config["seeds"].values()) else configuration

    @classmethod
    def execute(cls, configuration):
        seed, resolved = resolve_configuration(configuration)
        # Direct API random requests also save the actual seed for reproduction.
        unique_id = cls.hidden.unique_id
        if unique_id is not None:
            prompt_node = (cls.hidden.prompt or {}).get(str(unique_id))
            if prompt_node and "configuration" in prompt_node.get("inputs", {}):
                prompt_node["inputs"]["configuration"] = resolved
            workflow_node = get_workflow_node(cls.hidden.extra_pnginfo, str(unique_id))
            if workflow_node is not None:
                workflow_node["widgets_values"] = [resolved]
                if "widgets_values_named" in workflow_node:
                    workflow_node["widgets_values_named"]["configuration"] = resolved
        return io.NodeOutput(*seed, ui={"eclipse_seed_pair": [str(value) for value in seed]})
