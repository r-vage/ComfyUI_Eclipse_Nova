# List normalization, reservations and aligned outputs for the planner panel.
import folder_paths
from comfy_api.latest import io

from .node_debug import debug_event
from .shot_planner import (
    ShotPoolExhausted,
    ledger_path,
    plan_report,
    plan_shots,
    selected_shots,
)

_LOG_PREFIX = "ShotPlanner"


def single_setting(value, name):
    if isinstance(value, list):
        if len(value) != 1:
            raise ValueError(f"{name} requires one value; Shot Planner creates one plan per execution.")
        return value[0]
    return value


def combined_text(value, name):
    if isinstance(value, list):
        if any(not isinstance(part, str) for part in value):
            raise TypeError(f"{name} must contain only text.")
        return "\n\n".join(part for part in value if part.strip())
    return value


def execute_plan(*, mode, manual_shots=None, **settings):
    path = None if mode == "Manual" else ledger_path(folder_paths.get_output_directory(), settings["project"])
    try:
        plan = plan_shots(path, **settings, mode=mode, manual_shots=manual_shots)
    except ShotPoolExhausted as error:
        from comfy_execution.graph_utils import ExecutionBlocker

        message = str(error)
        debug_event(_LOG_PREFIX, "Coverage exhausted; stopping branch without saving a new batch")
        blocker = ExecutionBlocker(None)
        return io.NodeOutput(blocker, blocker, blocker, blocker, message,
                             ui={"eclipse_shot_planner_notice": [message], "eclipse_shot_planner_stopped": [True]})
    shots = selected_shots(plan)
    debug_event(_LOG_PREFIX, "Plan ready", selected=len(shots), exhausted=bool(plan.get("exhausted")),
                warnings=len(plan.get("warnings", [])), operation=plan["operation"], values=("operation",))
    return io.NodeOutput(plan, [shot["prompt"] for shot in shots], [shot["seed"] for shot in shots],
                         [shot["shot_id"] for shot in shots], plan_report(plan),
                         ui={"eclipse_shot_planner_notice": plan.get("warnings", []),
                             "eclipse_shot_planner_info": plan.get("info", []),
                             "eclipse_shot_planner_stopped": [plan["operation"] == "reserve" and bool(plan.get("exhausted"))]})
