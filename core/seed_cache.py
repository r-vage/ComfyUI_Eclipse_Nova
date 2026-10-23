# Cache automatic nodes according to the override actually used at execution.
# No images, pipes, model objects or resolved input values are retained here.
import hashlib
import inspect
import itertools
import json
import threading
import weakref
from collections import OrderedDict
from dataclasses import dataclass

from comfy_execution.graph_utils import is_link
from comfy_execution.utils import get_executing_context

_MAX_STATES = 512
_lock = threading.RLock()
_tokens = itertools.count(1)
_states = weakref.WeakKeyDictionary()
_pending = weakref.WeakValueDictionary()


@dataclass
class _State:
    token: int = 0
    automatic: bool = True
    evaluation: object = None
    recorded: bool = False
    pending_key: tuple | None = None


def _fingerprint_context():
    # ComfyUI deliberately omits linked values from fingerprint_inputs and does
    # not expose its cache scope through CurrentNodeContext. Inspect only the
    # enclosing IsChangedCache call, as Image Selector already does. Never
    # patch the executor or request/evaluate upstream nodes during this check.
    frame = inspect.currentframe()
    try:
        while frame is not None:
            evaluator = frame.f_locals.get("self")
            if type(evaluator).__name__ == "IsChangedCache":
                node_id = frame.f_locals.get("node_id")
                if node_id is not None and getattr(evaluator, "outputs_cache", None) is not None:
                    return evaluator, str(node_id)
            frame = frame.f_back
    finally:
        del frame


def _input_scope(prompt, node_id):
    # Separate graph/configuration revisions without depending on evaluation
    # order or another workflow's node IDs. Only this node's ancestors matter.
    sources = {}
    pending = [node_id]
    while pending:
        key = pending.pop()
        if key in sources:
            continue
        node = prompt.get_node(key)
        inputs = node.get("inputs", {})
        sources[key] = (node["class_type"], inputs)
        pending.extend(value[0] for value in inputs.values() if is_link(value))
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"),
                               default=lambda value: (type(value).__qualname__, id(value)))
    digest = hashlib.sha256()
    for part in encoder.iterencode(sources):
        digest.update(part.encode("utf-8"))
    return node_id, digest.digest()


def automatic_fingerprint():
    context = _fingerprint_context()
    if context is None:
        # Direct calls/older execution hosts cannot provide a scoped record.
        # Keep the existing automatic behavior rather than freezing a fallback.
        return float("nan")
    evaluator, node_id = context
    scope = _input_scope(evaluator.dynprompt, node_id)
    with _lock:
        entries = _states.setdefault(evaluator.outputs_cache, OrderedDict())
        state = entries.get(scope)
        if state is None:
            state = entries[scope] = _State()
        entries.move_to_end(scope)
        if state.evaluation is None or state.evaluation() is not evaluator:
            # One token per submission, including when a client reuses a prompt
            # ID. Holding this token after an override avoids an extra rerun.
            if state.automatic:
                state.token = next(_tokens)
            state.evaluation = weakref.ref(evaluator)
            state.recorded = False
            if state.pending_key is not None and _pending.get(state.pending_key) is state:
                _pending.pop(state.pending_key, None)
            state.pending_key = (evaluator.prompt_id, node_id)
            _pending[state.pending_key] = state
        while len(entries) > _MAX_STATES:
            entries.popitem(last=False)
        return state.token


def record_automatic_execution(automatic):
    context = get_executing_context()
    if context is None:
        return
    with _lock:
        state = _pending.get((context.prompt_id, context.node_id))
        evaluator = state.evaluation() if state is not None else None
        if evaluator is None or getattr(evaluator.outputs_cache, "is_changed_cache", None) is not evaluator:
            return
        # ComfyUI can map one node over several PIPE values. Any item using the
        # automatic fallback must keep that node eligible on the next queue.
        state.automatic = bool(automatic) or (state.recorded and state.automatic)
        state.recorded = True
