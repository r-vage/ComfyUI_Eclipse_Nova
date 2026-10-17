# One structured Shot Planner panel; external text lists remain one plan.
import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.shot_planner_configuration import (
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    resolve_inputs,
    validate_configuration,
)
from ..core.shot_planner_execution import execute_plan, single_setting


class RvText_CharacterShotPlanner(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Character Shot Planner [Eclipse Nova]", display_name="Character Shot Planner",
            category=CATEGORY.MAIN.value + CATEGORY.CHARACTER.value,
            description="One plan per execution. Planner creates compatible candidates with optional reservations; Manual consumes the whole text/list in order. Connected project and shared texts override the panel. The five outputs keep prompts, generation seeds and shot IDs aligned.",
            is_input_list=True, not_idempotent=True,
            inputs=[
                io.String.Input("project", optional=True, force_input=True, tooltip="Override the project label/history name. Requires one string. None uses the local value."),
                io.String.Input("character_lock", optional=True, force_input=True, tooltip="Override Character instructions, such as Character Sheet Pack's positive output. Text lists join into one shared lock."),
                io.String.Input("outfit_lock", optional=True, force_input=True, tooltip="Override shared wardrobe instructions. Text lists join with blank lines; None uses the local value."),
                io.String.Input("scene", optional=True, force_input=True, tooltip="Override the shared scene and lighting. Text lists join with blank lines; None uses the local value."),
                io.String.Input("manual_shots", optional=True, force_input=True, tooltip="Manual: override local shot text with multiline text or a STRING list. One nonempty line per shot; keeps order and duplicates. Planner ignores this input."),
                io.Int.Input("seed_input", optional=True, force_input=True, min=0, max=2**64 - 1,
                             tooltip="Use a shared planner seed. Connect to select Input seed; Local seed in the bar can override it. None uses the saved local seed. Output seeds belong to the individual shots."),
                io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration()),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec()}),
            ],
            outputs=[
                io.Custom("ECLIPSE_SHOT_PLAN").Output("plan", tooltip="Complete plan compatible with Shot Plan Slice. Manual contains no reservations."),
                io.String.Output("prompts", is_output_list=True, tooltip="One selected prompt per shot; connect to the dataset encoder."),
                io.Int.Output("seeds", is_output_list=True, tooltip="One seed per prompt; connect to the dataset sampler."),
                io.String.Output("shot_ids", is_output_list=True, tooltip="Stable aligned shot IDs for naming and captions."),
                io.String.Output("report", tooltip="Full plan report, including selected prompts, seeds, coverage and reservation details."),
            ],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(single_setting(configuration, "configuration"))
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, configuration, project=None, character_lock=None, outfit_lock=None,
                scene=None, manual_shots=None, seed_input=None):
        config = validate_configuration(single_setting(configuration, "configuration"))
        settings = resolve_inputs(config, project, character_lock, outfit_lock, scene, manual_shots, seed_input)
        result = execute_plan(**settings)
        # Keep only a small status in the editor. Full reports remain an output.
        ui = dict(result.ui)
        ui["eclipse_seed"] = [str(settings["seed"])]
        if isinstance(result.args[0], dict):
            plan = result.args[0]
            ui["eclipse_shot_plan"] = [{"project": plan["project"], "batch": plan["batch_id"],
                                        "count": len(result.args[1]), "mode": settings["mode"], "operation": plan["operation"]}]
        return io.NodeOutput(*result.args, ui=ui)
