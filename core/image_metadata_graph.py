# Read saved ComfyUI connections without executing nodes or importing their packs.

import json
import math

FIELDS = ("steps", "cfg_scale", "sampler_name", "scheduler", "seed", "text_pos", "text_neg")
ALIASES = {"cfg_scale": ("cfg", "cfg_scale"), "seed": ("seed", "noise_seed"),
           "text_pos": ("text_pos",), "text_neg": ("text_neg",)}
MAX_NODES = 10000


def metadata_object(value):
    if isinstance(value, str):
        if len(value) > 8 * 1024 * 1024:
            return {}
        try:
            value = json.loads(value)
        except (ValueError, RecursionError):
            return {}
    return value if isinstance(value, dict) else {}


def _consensus(values):
    # Missing or disagreeing branches cannot establish a reliable value.
    return values[0] if values and values[0] is not None and all(value == values[0] for value in values) else None


def _workflow_graph(workflow):
    nodes = workflow.get("nodes", [])
    if not isinstance(nodes, list) or len(nodes) > MAX_NODES:
        return {}, {}
    links = workflow.get("links", [])
    links = {link[0]: [str(link[1]), link[2]] for link in links
             if isinstance(link, list) and len(link) >= 6 and isinstance(link[0], (str, int))} if isinstance(links, list) else {}
    graph, outputs = {}, {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), (int, str)) or node.get("mode", 0) in (2, 4):
            continue
        key = str(node["id"])
        kind = node.get("type", "")
        if not isinstance(kind, str):
            continue
        widgets = node.get("widgets_values", [])
        inputs = {}
        if isinstance(widgets, list):
            if widgets and metadata_object(widgets[0]).get("version"):
                inputs["configuration"] = widgets[0]
            else:
                names = {"KSampler": ["seed", "steps", "cfg", "sampler_name", "scheduler", "denoise"],
                         "KSamplerAdvanced": ["add_noise", "noise_seed", "steps", "cfg", "sampler_name", "scheduler", "start_at_step", "end_at_step", "return_with_leftover_noise"],
                         "SamplerCustom": ["add_noise", "noise_seed", "cfg"],
                         "RandomNoise": ["noise_seed"], "KSamplerSelect": ["sampler_name"],
                         "BasicScheduler": ["scheduler", "steps", "denoise"], "CFGGuider": ["cfg"],
                         "CLIPTextEncode": ["text"]}.get(kind, [])
                values = list(widgets)
                # control_after_generate is a frontend widget, not a sampler input.
                offset = 2 if kind in ("KSamplerAdvanced", "SamplerCustom") else 1
                if kind in ("KSampler", "KSamplerAdvanced", "SamplerCustom", "RandomNoise") and len(values) > offset and values[offset] in ("fixed", "randomize", "increment", "decrement"):
                    values.pop(offset)
                inputs.update(zip(names, values))
                if kind.startswith("Seed ") and values:
                    inputs["seed"] = values[0]
        for entry in node.get("inputs", []) if isinstance(node.get("inputs"), list) else []:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str) and isinstance(entry.get("link"), (str, int)) and entry["link"] in links:
                inputs[entry["name"]] = links[entry["link"]]
        outputs[key] = [entry.get("name", "") if isinstance(entry, dict) else "" for entry in node.get("outputs", [])] if isinstance(node.get("outputs"), list) else []
        graph[key] = {"class_type": kind, "inputs": inputs}
    return graph, outputs


class _GraphReader:
    def __init__(self, graph, outputs):
        self.graph = graph
        self.outputs = outputs
        self.cache = {}

    def link(self, value):
        return isinstance(value, list) and len(value) == 2 and isinstance(value[0], (int, str)) and str(value[0]) in self.graph and type(value[1]) is int

    def value(self, value, field, trail):
        if self.link(value):
            outputs = self.outputs.get(str(value[0]), [])
            name = outputs[value[1]] if 0 <= value[1] < len(outputs) else ""
            names = (*FIELDS, "cfg", "noise_seed", "width", "height", "denoise")
            if name in names and name not in ALIASES.get(field, (field,)) and name != field:
                return None
            return self.read(str(value[0]), field, trail)
        if isinstance(value, dict) and field == "seed":
            return value.get("value") if value.get("policy", "fixed") in ("fixed", "increment", "decrement") else None
        return value if isinstance(value, (str, int, float)) and not isinstance(value, bool) else None

    def read(self, key, field, trail=()):
        token = (key, field)
        if token in trail or len(trail) >= 48:
            return None
        if token in self.cache:
            return self.cache[token]
        result = self._read(key, field, (*trail, token))
        self.cache[token] = result
        return result

    def _read(self, key, field, trail):
        node = self.graph.get(key, {})
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            return None
        kind = node.get("class_type", "")
        config = metadata_object(inputs.get("configuration"))
        parameters = config.get("parameters", config.get("sampler", {}))
        parameters = parameters if isinstance(parameters, dict) else {}
        pipe = inputs.get("pipe", inputs.get("pipe_opt"))
        if parameters.get("allow_overwrite") or inputs.get("allow_overwrite"):
            result = self.value(pipe, field, trail)
            if result is not None:
                return result
        for name in ALIASES.get(field, (field,)):
            if name in inputs:
                return self.value(inputs[name], field, trail)
            if name in parameters:
                return self.value(parameters[name], field, trail)
            if name in config:
                return self.value(config[name], field, trail)
        if field in ("text_pos", "text_neg"):
            if kind == "ConditioningZeroOut":
                return ""
            for name in ("positive" if field == "text_pos" else "negative", "conditioning"):
                if name in inputs:
                    return self.value(inputs[name], field, trail)
            if kind.startswith("CLIPTextEncode") and "text" in inputs:
                return self.value(inputs["text"], field, trail)
        # Native custom samplers keep values in their connected helper nodes.
        route = {"seed": "noise", "steps": "sigmas", "scheduler": "sigmas", "cfg_scale": "guider",
                 "sampler_name": "sampler", "text_pos": "guider", "text_neg": "guider"}.get(field)
        if route in inputs:
            return self.value(inputs[route], field, trail)
        if pipe is not None:
            return self.value(pipe, field, trail)
        branches = [value for name, value in inputs.items() if name.startswith("any_") and self.link(value)]
        if branches:
            return _consensus([self.value(value, field, trail) for value in branches])
        if kind.startswith(("Primitive", "Seed ")) and "value" in inputs:
            return self.value(inputs["value"], field, trail)
        return None


def _valid(field, value):
    if field in ("text_pos", "text_neg"):
        return value if isinstance(value, str) else None
    if field in ("sampler_name", "scheduler"):
        return value if isinstance(value, str) and value.strip() else None
    try:
        if field in ("seed", "steps"):
            if isinstance(value, str) and value.isdecimal():
                value = int(value)
            limit = 2**64 - 1 if field == "seed" else 1000000
            return value if type(value) is int and (0 if field == "seed" else 1) <= value <= limit else None
        return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None
    except (ValueError, OverflowError):
        return None


def graph_metadata(prompt, workflow, known):
    workflow_graph, outputs = _workflow_graph(metadata_object(workflow))
    api = metadata_object(prompt)
    graph = {str(key): value for key, value in api.items() if isinstance(value, dict) and isinstance(value.get("class_type"), str)} if len(api) <= MAX_NODES else {}
    graph = graph or workflow_graph
    # Nova records resolved random seeds in workflow configuration after execution.
    for key, node in graph.items():
        inputs = node.get("inputs", {})
        config = metadata_object(inputs.get("configuration")) if isinstance(inputs, dict) else {}
        saved = metadata_object(workflow_graph.get(key, {}).get("inputs", {}).get("configuration"))
        if isinstance(config.get("seed"), dict) and config["seed"].get("policy") == "random" and isinstance(saved.get("seed"), dict) and saved["seed"].get("policy") == "fixed":
            graph[key] = {**node, "inputs": {**inputs, "configuration": {**config, "seed": saved["seed"]}}}
    reader = _GraphReader(graph, outputs)
    # If an image saver exists, exclude unrelated samplers elsewhere on the canvas.
    roots = [key for key, node in graph.items() if node.get("class_type", "").startswith(("SaveImage", "Save Images"))]
    reachable = set()
    pending = roots[:]
    while pending:
        key = pending.pop()
        if key in reachable:
            continue
        reachable.add(key)
        inputs = graph.get(key, {}).get("inputs", {})
        if isinstance(inputs, dict):
            pending.extend(str(value[0]) for value in inputs.values() if reader.link(value))
    candidates = []
    for key, node in graph.items():
        kind = node.get("class_type", "")
        if roots and key not in reachable:
            continue
        if kind not in ("KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced") and not kind.startswith(("Eclipse KSampler", "KSampler Pipe")):
            continue
        values = {field: _valid(field, reader.read(key, field)) for field in FIELDS}
        matching = [field for field in ("steps", "cfg_scale", "sampler_name", "scheduler", "seed") if field in known and values[field] is not None]
        if any(known[field] != values[field] for field in matching):
            continue
        candidates.append((len(matching), values))
    if not candidates:
        return {}
    best = max(score for score, _ in candidates)
    selected = [values for score, values in candidates if score == best]
    return {field: value for field in FIELDS if (value := _consensus([candidate[field] for candidate in selected])) is not None}
