from __future__ import annotations
from comfy_api.latest import io  # type: ignore
from ..core import CATEGORY
from ..core.logger import log
from ..core.lazy_switch import select_switch_input

_LOG_PREFIX = "AnyMultiSwitch_Lazy"


class RvRouter_Any_MultiSwitch_lazy(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        type_template = io.MatchType.Template("any_type")
        return io.Schema(
            node_id="Any Multi-Switch Lazy [Eclipse Nova]",
            display_name="Any Multi-Switch Lazy",
            category=CATEGORY.MAIN.value + CATEGORY.ROUTER.value,
            description=(
                "Multi-switch for ANY inputs with lazy evaluation. "
                "Evaluates connected slots in order until one returns data. "
                "Later upstream branches are skipped entirely. "
                "Inputs update automatically when inputcount changes."
            ),
            is_input_list=True,
            inputs=[
                io.Int.Input(
                    "inputcount",
                    default=2,
                    min=1,
                    max=64,
                    step=1,
                    socketless=True,
                    tooltip="Number of ANY inputs to expose. Inputs update automatically.",
                ),
                *[io.MatchType.Input(
                    f"any_{index}", template=type_template, optional=True, lazy=True,
                    tooltip=f"Any input #{index}; used when earlier slots are empty or disconnected.",
                ) for index in range(1, 65)],
            ],
            outputs=[
                io.MatchType.Output(
                    type_template, id="*", is_output_list=True, tooltip="The selected output."
                ),
            ],
            hidden=[io.Hidden.unique_id, io.Hidden.prompt, io.Hidden.dynprompt, io.Hidden.execution_list],
        )

    @classmethod
    def check_lazy_status(cls, inputcount=2, **kwargs):
        return select_switch_input(inputcount, kwargs, cls.hidden)[2]

    @classmethod
    def execute(cls, inputcount, **kwargs):
        tag = f"{_LOG_PREFIX} #{cls.hidden.unique_id}"

        key, value, _ = select_switch_input(inputcount, kwargs)
        if key is not None:
            log.debug(tag, f"Passing slot {key}")
            return io.NodeOutput(value)
        log.debug(tag, "All slots disconnected or empty, passing None")
        return io.NodeOutput([None])
