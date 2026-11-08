# Cache automatic nodes according to the override actually used at execution.
# No images, pipes, model objects or resolved input values are retained here.
import itertools
import threading
import weakref
from collections import OrderedDict
from dataclasses import dataclass

from comfy_execution.utils import get_executing_context

from .execution_cache import fingerprint_context, input_scope

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


def automatic_fingerprint():
    context = fingerprint_context()
    if context is None:
        # Direct calls/older execution hosts cannot provide a scoped record.
        # Keep the existing automatic behavior rather than freezing a fallback.
        return float("nan")
    evaluator, node_id = context
    scope = input_scope(evaluator.dynprompt, node_id)
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
