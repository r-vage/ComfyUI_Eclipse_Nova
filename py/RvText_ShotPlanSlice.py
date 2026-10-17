# Select an aligned range from a Character Shot Planner plan.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.node_debug import debug_event, debug_node
from ..core.operation_panel import OperationPanel
from ..core.shot_planner import selected_shots

_LOG_PREFIX = "ShotPlanner"


class RvText_ShotPlanSlice(OperationPanel, io.ComfyNode):
    PANEL_KIND = "shot_slice"

    @classmethod
    def operation_schema(cls):
        return io.Schema(
            node_id="Shot Plan Slice [Eclipse Nova]",
            display_name="Shot Plan Slice",
            category=CATEGORY.MAIN.value + CATEGORY.CHARACTER.value,
            description="Send a range of selected shots from an existing plan to a generation branch. Keeps prompts, seeds and IDs aligned; does not create or release reservations. Useful for splitting a batch or retrying a failed range.",
            inputs=[
                io.Custom("ECLIPSE_SHOT_PLAN").Input("plan", tooltip="Connect Character Shot Planner's plan output. The slice returns selected shots only, not the skipped close/mid/wide alternatives."),
                io.Int.Input("start", default=0, min=0, max=99, tooltip="Zero-based position within this plan: 0 starts at its first shot, even when manual_start is 26. Must be inside ordinary Planner plans; Manual and final coverage plans skip branches beyond the end."),
                io.Int.Input("count", default=0, min=0, max=100, tooltip="Number of selected shots; 0 means all remaining. For a 50-shot plan, start=25/count=25 returns shots 26–50. Manual and final coverage plans truncate to remaining shots or skip empty branches. Other Planner ranges must fit the plan. IDs, seeds and reservations stay unchanged."),
            ],
            outputs=[
                io.String.Output("prompts", is_output_list=True, tooltip="Selected prompts for this range, in their original order. Connect to this branch's text encoder."),
                io.Int.Output("seeds", is_output_list=True, tooltip="Matching generation seeds for this range. Connect to the same branch's sampler."),
                io.String.Output("shot_ids", is_output_list=True, tooltip="Original shot IDs for this range; slicing does not renumber shots. Aligned with the returned prompts and seeds."),
            ],
        )

    @classmethod
    @debug_node(_LOG_PREFIX)
    def execute_operation(cls, plan, start, count):
        shots = selected_shots(plan, start, count)
        debug_event(_LOG_PREFIX, "Slice selected", start=start, requested=count, selected=len(shots))
        if not shots:
            from comfy_execution.graph_utils import ExecutionBlocker  # type: ignore

            blocker = ExecutionBlocker(None)
            return io.NodeOutput(blocker, blocker, blocker)
        return io.NodeOutput([s["prompt"] for s in shots], [s["seed"] for s in shots],
                             [s["shot_id"] for s in shots])
