# Shared selection for lazy routing and execution. List-input nodes receive
# unresolved links as (None,), and resolved empty outputs as [None], [""], or [].
# Query the execution cache when available instead of guessing from container type.
from .image_helpers import unwrap_value


def valid_switch_value(value):
    if value is None:
        return False
    if isinstance(value, (list, tuple)):
        return any(valid_switch_value(item) for item in value)
    if isinstance(value, (str, dict)):
        return len(value) > 0
    return True


def select_switch_input(inputcount, values, hidden=None):
    count = max(1, min(64, int(unwrap_value(inputcount, 2))))
    node_data = None
    if hidden is not None:
        unique_id = str(hidden.unique_id)
        dynprompt = getattr(hidden, "dynprompt", None)
        if dynprompt is not None:
            node_data = dynprompt.get_node(unique_id)
        if node_data is None:
            prompt = getattr(hidden, "prompt", None) or {}
            node_data = prompt.get(unique_id)
            for delimiter in (":", "."):
                if node_data is None:
                    node_data = prompt.get(unique_id.split(delimiter)[-1])
    connected = node_data.get("inputs", {}) if node_data else {}
    for index in range(1, count + 1):
        key = f"any_{index}"
        value = values.get(key)
        if valid_switch_value(value):
            return key, value, []
        link = connected.get(key)
        if isinstance(link, list) and len(link) == 2:
            execution_list = getattr(hidden, "execution_list", None)
            if execution_list is not None:
                cached = execution_list.get_cache(link[0], str(hidden.unique_id))
                unresolved = cached is None or cached.outputs is None
            else:
                unresolved = value is None or (isinstance(value, tuple) and value == (None,))
            if unresolved:
                return None, None, [key]
    return None, None, []
