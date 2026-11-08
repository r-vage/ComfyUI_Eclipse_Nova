# Eclipse-owned incremental graph expansion. No third-party loop nodes.
import threading
import weakref
from dataclasses import dataclass, replace
from uuid import uuid4

from comfy_execution.graph_utils import ExecutionBlocker, GraphBuilder, is_link
from comfy_execution.utils import get_executing_context

LOOP_TYPE = "ECLIPSE_LOOP"
STOP_CONTROL_TYPE = "ECLIPSE_LOOP_CONTROL"
ITERATION_ID = "Loop Iteration [Eclipse Nova]"
_controls = weakref.WeakValueDictionary()
_lock = threading.Lock()


def missing_input(value):
    return value is None or isinstance(value, (list, tuple)) and len(value) == 1 and value[0] is None


@dataclass(frozen=True)
class LoopControlTarget:
    node_id: str


class LoopControl:
    def __init__(self, node_id, control_node_id=None):
        context = get_executing_context()
        self.prompt_id = context.prompt_id if context else ""
        self.node_id = node_id
        self.control_node_id = control_node_id
        self.token = uuid4().hex
        self.stop = threading.Event()
        self.active = True
        with _lock:
            _controls[self.token] = self


def request_stop(token, prompt_id):
    with _lock:
        control = _controls.get(token)
        if control is None or not control.active or control.prompt_id != prompt_id:
            return False
        control.stop.set()
    _publish(control, "stopping")
    return True


@dataclass(frozen=True)
class LoopState:
    opener: str
    index: int
    end: int
    queue_end: int
    carry: list
    control: LoopControl
    render: object = None
    storage: object = None
    report: str = ""


def _publish(control, status, **details):
    from server import PromptServer

    server = PromptServer.instance
    if server is not None:
        server.send_sync("eclipse-nova.loop", {
            "node_id": control.node_id, "control_node_id": control.control_node_id,
            "prompt_id": control.prompt_id, "token": control.token,
            "status": status, **details,
        }, server.client_id)


def progress(state, status="running"):
    _publish(state.control, status, index=state.index, total=state.end)


def begin_loop(node_id, total, start=0, limit=0, carry=None, render=None, storage=None, report="", stop_control=None):
    if any(type(v) is not int or v < 0 for v in (total, start, limit)) or start > total:
        raise ValueError("Loop range requires 0 ≤ start_index ≤ total; parts_per_queue must be nonnegative.")
    if stop_control is not None and not isinstance(stop_control, LoopControlTarget):
        raise TypeError("Connect Loop Control to stop_control.")
    control_node_id = stop_control.node_id if stop_control is not None else None
    end = min(total, start + limit) if limit else total
    state = LoopState(str(node_id), start, total, end, [None] if carry is None else carry,
                      LoopControl(str(node_id), control_node_id), render, storage, report)
    progress(state)
    return state


def iteration_values(state):
    active = state.index < state.queue_end
    index = state.index if active else ExecutionBlocker(None)
    carried = state.carry[0] if len(state.carry) == 1 else state.carry
    values = (state, index, carried)
    data = state.render
    if data is None:
        return (*values, *([None] * 14))
    return (*values, data.plan, data.images, data.audio, data.conditioning_audio,
            data.prompts, data.first_part_prompt, data.width, data.height,
            data.reference_mode, data.visual_condition_strength, state.storage,
            active, state.report, data.fps)


def _body(dynprompt, opener, closer):
    # Only nodes on dependency paths from this opener to this closer belong to
    # the body. Previews/side effects must feed End explicitly. Get/Set links
    # have already been resolved by ComfyUI before this traversal.
    parents, children = {}, {}
    pending = [closer]
    while pending:
        key = pending.pop()
        if key in parents:
            continue
        values = dynprompt.get_node(key).get("inputs", {}).values()
        parents[key] = {value[0] for value in values if is_link(value)}
        for parent in parents[key]:
            children.setdefault(parent, set()).add(key)
        if key != opener:
            pending.extend(parents[key])
    if opener not in parents:
        raise ValueError("Loop End must receive the matching Loop Start and a result from its body.")
    contained, pending = set(), [opener]
    while pending:
        key = pending.pop()
        if key in contained:
            continue
        contained.add(key)
        pending.extend(children.get(key, ()))
    if closer not in contained:
        raise ValueError("Loop End is outside this loop's dependency path.")
    return contained - {opener}


def close_loop(state, value, dynprompt, unique_id, incomplete="return partial"):
    from comfy_api.latest import io

    if not isinstance(state, LoopState):
        raise TypeError("Connect an Eclipse Loop Start to Loop End.")
    context = get_executing_context()
    if context is not None and state.control.prompt_id != context.prompt_id:
        # A cached start belongs to an older queue. A stop token never crosses queues.
        state = replace(state, control=LoopControl(state.control.node_id, state.control.control_node_id))
    active = state.index < state.queue_end
    carry = value if active else state.carry
    if carry is None:
        raise ValueError("Loop End needs the completed iteration's value.")
    next_index = state.index + int(active)
    path = ""
    if state.render is not None:
        from .video_checkpoint import verify_part

        path = verify_part(state.render, carry, next_index, state.storage)
    done = next_index >= state.end
    stopped = next_index >= state.queue_end or state.control.stop.is_set()
    if done or stopped:
        state.control.active = False
        progress(replace(state, index=next_index), "complete" if done else "stopped")
        output = carry[0] if len(carry) == 1 else carry
        if not done and incomplete == "block downstream":
            output = ExecutionBlocker(None)
        audio = state.render.audio if state.render is not None else None
        from .video_checkpoint import caption_context

        captions = caption_context(state.render) if state.render is not None else None
        report = f"{'Complete' if done else 'Stopped'}: {next_index} / {state.end} parts."
        if path:
            report += f"\nSaved run: {path}"
        return io.NodeOutput(output, next_index, done, path,
                             report, audio, captions)

    graph = GraphBuilder()
    iteration = graph.node(ITERATION_ID, "iteration")
    next_state = replace(state, opener=iteration.id, index=next_index, carry=carry)
    iteration.set_input("state", next_state)
    iteration.set_override_display_id(state.control.node_id)
    contained = _body(dynprompt, state.opener, str(unique_id))
    copies = {}
    for key in sorted(contained):
        original = dynprompt.get_node(key)
        copy = graph.node(original["class_type"], "end" if key == str(unique_id) else key)
        copy.set_override_display_id(dynprompt.get_display_node_id(key))
        copies[key] = copy
    for key, copy in copies.items():
        for name, item in dynprompt.get_node(key).get("inputs", {}).items():
            if is_link(item) and item[0] == state.opener:
                item = iteration.out(item[1])
            elif is_link(item) and item[0] in copies:
                item = copies[item[0]].out(item[1])
            copy.set_input(name, item)
    end = copies[str(unique_id)]
    return io.NodeOutput(*(end.out(i) for i in range(7)), expand=graph.finalize())


def loop_outputs(video=False):
    from comfy_api.latest import io

    outputs = [io.Custom(LOOP_TYPE).Output("loop"), io.Int.Output("index", tooltip="Absolute zero-based index, including retained parts."),
               io.AnyType.Output("previous", tooltip="Carried state from the previous completed iteration, including an intact list or PIPE.")]
    if video:
        from .video_run import STORAGE_TYPE

        outputs.extend([io.AnyType.Output("plan"), io.Image.Output("images"), io.Audio.Output("audio"),
                        io.Audio.Output("conditioning_audio"), io.AnyType.Output("prompts"),
                        io.String.Output("first_part_prompt"), io.Int.Output("width"), io.Int.Output("height"),
                        io.AnyType.Output("reference_mode"), io.Float.Output("visual_condition_strength"),
                        io.Custom(STORAGE_TYPE).Output("storage"), io.Boolean.Output("render"),
                        io.String.Output("report"), io.Float.Output("fps")])
    return outputs
