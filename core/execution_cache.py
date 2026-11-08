# Read-only cache scope shared by execution-dependent fingerprints.
import hashlib
import inspect
import json

from comfy_execution.graph_utils import is_link


def fingerprint_context():
    # ComfyUI omits linked values and cache scope from fingerprint_inputs. Read
    # its enclosing evaluation only; never patch or evaluate upstream nodes.
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


def input_scope(prompt, node_id):
    # Only ancestors define this node's scope; downstream styling/reordering
    # must not invalidate upstream media. Separate workflows sharing node IDs.
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
