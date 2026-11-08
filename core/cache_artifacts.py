# Invalidate a cached producer when its externally removable files disappear.
# Track weak owners and paths only; never retain images, videos or model objects.
import itertools
import os
import threading
import weakref
from collections import OrderedDict
from dataclasses import dataclass, field

from comfy_execution.utils import get_executing_context

from .execution_cache import fingerprint_context, input_scope

_MAX_STATES = 512
_lock = threading.RLock()
_tokens = itertools.count(1)
_states = weakref.WeakKeyDictionary()
_pending = weakref.WeakValueDictionary()


@dataclass
class _State:
    token: int
    artifacts: list = field(default_factory=list)
    evaluation: object = None
    pending_key: tuple | None = None


def artifact_fingerprint(base=False):
    context = fingerprint_context()
    if context is None:
        return base
    evaluator, node_id = context
    scope = input_scope(evaluator.dynprompt, node_id)
    with _lock:
        entries = _states.setdefault(evaluator.outputs_cache, OrderedDict())
        state = entries.get(scope)
        if state is None:
            state = entries[scope] = _State(next(_tokens))
        entries.move_to_end(scope)
        if state.evaluation is None or state.evaluation() is not evaluator:
            live = [(owner, paths) for owner, paths in state.artifacts if owner() is not None]
            if any(not os.path.exists(path) for _, paths in live for path in paths):
                # A new stable token invalidates the producer and downstream
                # cache entries once. Successful rebuilding keeps that token.
                state.token = next(_tokens)
                live = []
            state.artifacts = live
            state.evaluation = weakref.ref(evaluator)
            if state.pending_key is not None and _pending.get(state.pending_key) is state:
                _pending.pop(state.pending_key, None)
            state.pending_key = evaluator.prompt_id, node_id
            _pending[state.pending_key] = state
        while len(entries) > _MAX_STATES:
            entries.popitem(last=False)
        return base, state.token


def record_artifacts(owner, paths):
    context = get_executing_context()
    if context is None:
        return
    with _lock:
        state = _pending.get((context.prompt_id, context.node_id))
        evaluator = state.evaluation() if state is not None else None
        if evaluator is None or getattr(evaluator.outputs_cache, "is_changed_cache", None) is not evaluator:
            return
        # Keep all still-cached variants (e.g. an upstream runtime fingerprint
        # changed without changing the graph). LRU can select an older output.
        state.artifacts = [(reference, files) for reference, files in state.artifacts
                           if reference() is not None and reference() is not owner]
        state.artifacts.append((weakref.ref(owner), tuple(os.fspath(path) for path in paths)))
