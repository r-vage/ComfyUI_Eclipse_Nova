# A live stop button can stay on the main canvas while its loop is in a subgraph.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.loop import STOP_CONTROL_TYPE, LoopControlTarget


class RvLogic_LoopControl(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Loop Control [Eclipse Nova]", display_name="Loop Control",
            category=CATEGORY.MAIN.value + CATEGORY.TOOLS.value,
            description="Live Stop after current part button for an Eclipse loop. Keep this node outside a subgraph and connect its control output, directly or through Get/Set, to Loop Start or Video Loop Start's stop_control input. The current part finishes saving and previewing before the loop stops. Use a separate control for each independently running loop.",
            outputs=[io.Custom(STOP_CONTROL_TYPE).Output("control", tooltip="Connect to the loop's optional stop_control input before queueing. The button sends a live stop request while that loop runs; it does not change generation inputs or seeds.")],
            # This output identifies this node; equal empty inputs on another
            # controller must not share its cached binding.
            hidden=[io.Hidden.unique_id], not_idempotent=True)

    @classmethod
    def execute(cls):
        return io.NodeOutput(LoopControlTarget(str(cls.hidden.unique_id)))
