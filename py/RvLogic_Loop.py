# Native V3 loop controls, shared by analysis and video generation.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_helpers import unwrap_value
from ..core.loop import (
    LOOP_TYPE,
    STOP_CONTROL_TYPE,
    begin_loop,
    close_loop,
    iteration_values,
    loop_outputs,
    missing_input,
    progress,
)


class RvLogic_LoopStart(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Loop Start [Eclipse Nova]", display_name="Loop Start",
            category=CATEGORY.MAIN.value + CATEGORY.TOOLS.value,
            description="Sequential Eclipse-owned loop. Connect loop to Loop End, index to the body, and End's value to the completed iteration result. No Easy-Use installation is needed.",
            inputs=[io.Int.Input("total", default=1, min=0, max=1000000, tooltip="Exclusive ending index. Zero skips the body and returns the initial value."),
                    io.Int.Input("start_index", default=0, min=0, max=1000000, tooltip="Absolute index of the first iteration. Supply matching initial state when starting later."),
                    io.Int.Input("parts_per_queue", default=0, min=0, max=1000000, tooltip="0 runs to the end. A positive value returns after that many completed iterations."),
                    io.Boolean.Input("cache_iterations", default=True, tooltip="Reuse unchanged completed work. Disable to execute the loop again on every queue."),
                    io.AnyType.Input("initial_value", optional=True, tooltip="Initial carried value or PIPE. The next iteration receives Loop End's value."),
                    io.Custom(STOP_CONTROL_TYPE).Input("stop_control", optional=True, tooltip="Optional Loop Control button, directly or through Get/Set. Put the control on the main canvas when this loop is inside a subgraph.")],
            outputs=loop_outputs(), hidden=[io.Hidden.unique_id], is_input_list=True)

    @classmethod
    def fingerprint_inputs(cls, cache_iterations=True, **kwargs):
        enabled = cache_iterations[0] if isinstance(cache_iterations, list) else cache_iterations
        return False if enabled else float("nan")

    @classmethod
    def execute(cls, total, start_index, parts_per_queue, cache_iterations, initial_value=None, stop_control=None):
        state = begin_loop(cls.hidden.unique_id, total[0], start_index[0], parts_per_queue[0], initial_value,
                           stop_control=unwrap_value(stop_control))
        return io.NodeOutput(*iteration_values(state)[:3])


class RvLogic_LoopIteration(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Loop Iteration [Eclipse Nova]", display_name="Loop Iteration",
            inputs=[io.Custom(LOOP_TYPE).Input("state")], outputs=loop_outputs(video=True), is_dev_only=True)

    @classmethod
    def execute(cls, state):
        progress(state)
        return io.NodeOutput(*iteration_values(state))


class RvLogic_LoopEnd(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Loop End [Eclipse Nova]", display_name="Loop End",
            category=CATEGORY.MAIN.value + CATEGORY.TOOLS.value,
            description="Complete one iteration, then continue or return its accumulated result. Put the accumulated preview before End to inspect warmup trims and joins before stopping. Saved video parts remain recoverable even if preview is interrupted.",
            inputs=[io.Custom(LOOP_TYPE).Input("loop", tooltip="Connect the matching Eclipse Loop Start or Video Loop Start."),
                    io.AnyType.Input("value", lazy=True, optional=True, tooltip="Completed iteration result, usually the accumulated preview's passthrough. Requested only when an iteration is needed."),
                    io.Combo.Input("incomplete", options=["return partial", "block downstream"], default="return partial",
                        tooltip="Return partial enables preview/export of stopped video runs. Block downstream prevents a full-analysis saver from consuming an unfinished description list.")],
            outputs=[io.AnyType.Output("value"), io.Int.Output("next_index"),
                     io.Boolean.Output("complete"), io.String.Output("run_path"), io.String.Output("report"),
                     io.Audio.Output("audio", tooltip="Selected master soundtrack for video runs; native generated audio remains in VIDEO."),
                     io.Custom("PIPE").Output("caption_context", tooltip="Saved full recording and excerpt start for IO Lyric Captions. Connect the accumulated video as its background to use H3-generated sound when no recording was supplied.")],
            hidden=[io.Hidden.dynprompt, io.Hidden.unique_id], enable_expand=True, is_input_list=True)

    @classmethod
    def check_lazy_status(cls, loop, value=None, **kwargs):
        return ["value"] if loop[0].index < loop[0].queue_end and missing_input(value) else []

    @classmethod
    def execute(cls, loop, incomplete, value=None):
        return close_loop(loop[0], value, cls.hidden.dynprompt, cls.hidden.unique_id, incomplete[0])
