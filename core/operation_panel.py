# Structured panels expose one configuration widget and explicit data/override
# sockets. Each node owns its parameter description and processing method.
import copy
import json
import math

from comfy_api.latest import io

from .operation_panel_layouts import CHOICE_LABELS, LABELS, LAYOUTS

WIDGET_TYPE = "ECLIPSE_NOVA_OPERATION"
_SCALARS = {"INT", "FLOAT", "BOOLEAN", "STRING", "COMBO"}


def _scalar(value):
    # List-input operations use one settings record for the full input batch.
    while isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return value


def editor_spec(schema, kind):
    layout = copy.deepcopy(LAYOUTS[kind])
    fields = {}
    for field in schema.inputs:
        if field.io_type not in _SCALARS or getattr(field, "force_input", False):
            continue
        value = {"type": field.io_type, "label": LABELS.get(field.id, field.id.replace("_", " ").capitalize()),
                 "tip": field.tooltip or "", "default": getattr(field, "default", None)}
        if field.io_type == "COMBO":
            value["options"] = list(field.options)
            if value["default"] is None:
                value["default"] = value["options"][0] if value["options"] else ""
        for key in ("min", "max", "step", "multiline"):
            setting = getattr(field, key, None)
            if setting is not None:
                value[key] = setting
        if field.id in layout.get("multiline", []):
            value["multiline"] = True
        fields[field.id] = value
    return {"family": "operation", "kind": kind, "title": schema.display_name,
            "nodeId": schema.node_id,
            "fields": fields, "layout": layout, "choiceLabels": CHOICE_LABELS}


def default_configuration(spec):
    return {"version": 1, "kind": spec["kind"],
            "parameters": {key: copy.deepcopy(field["default"]) for key, field in spec["fields"].items()}}


def _validate_value(value, field):
    kind, label = field["type"], field["label"]
    if kind in ("INT", "FLOAT"):
        if type(value) not in (int, float) or (isinstance(value, float) and not math.isfinite(value)):
            raise ValueError(f"{label} must be a finite number.")
        if kind == "INT" and int(value) != value:
            raise ValueError(f"{label} must be an integer.")
        if ("min" in field and value < field["min"]) or ("max" in field and value > field["max"]):
            raise ValueError(f"{label} is outside its supported range.")
        return int(value) if kind == "INT" else value
    if kind == "BOOLEAN":
        if type(value) is not bool:
            raise ValueError(f"{label} must be enabled or disabled.")
    elif not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    elif kind == "COMBO" and value not in field["options"]:
        raise ValueError(f"{label}: unavailable selection {value!r}.")
    return value


def validate_configuration(raw, spec):
    raw = _scalar(raw)
    if not isinstance(raw, str) or len(raw) > 1048576:
        raise ValueError("Configuration must be JSON text smaller than 1 MiB.")
    try:
        config = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid configuration JSON.") from error
    if (spec["kind"] == "wan_planner" and isinstance(config, dict)
            and config.get("version") == 1 and config.get("kind") == "wan_planner"
            and isinstance(config.get("parameters"), dict)
            and set(config["parameters"]) == set(spec["fields"]) - {"warmup_seconds"}):
        config["parameters"]["warmup_seconds"] = 0.0
    if (spec["kind"] == "transcribe" and isinstance(config, dict)
            and config.get("version") == 1 and config.get("kind") == "transcribe"
            and isinstance(config.get("parameters"), dict)):
        for key, default in (("stop", False), ("word_timing", "whisper")):
            if key in spec["fields"]:
                config["parameters"].setdefault(key, default)
    if (not isinstance(config, dict) or set(config) != {"version", "kind", "parameters"}
            or type(config["version"]) is not int or config["version"] != 1 or config["kind"] != spec["kind"]
            or not isinstance(config["parameters"], dict) or set(config["parameters"]) != set(spec["fields"])):
        raise ValueError(f"Expected version 1 {spec['title']} configuration.")
    return {key: _validate_value(config["parameters"][key], field) for key, field in spec["fields"].items()}


class OperationPanel:
    # The operation schema describes parameters and data contracts; only the
    # structured schema below is registered with ComfyUI. Processing uses the
    # current node's execution context without retaining another node class.
    PANEL_KIND = ""

    @classmethod
    def _panel_spec(cls):
        return editor_spec(cls.operation_schema(), cls.PANEL_KIND)

    @classmethod
    def define_schema(cls):
        schema = cls.operation_schema()
        spec = editor_spec(schema, cls.PANEL_KIND)
        scalar_fields = {field.id: field for field in schema.inputs if field.id in spec["fields"]}
        inputs = [field for field in schema.inputs if field.id not in scalar_fields]
        for key in spec["layout"].get("overrides", []):
            field = scalar_fields[key]
            tip = (field.tooltip or "") + " Connected non-None values override the panel."
            args = {"optional": True, "force_input": True, "tooltip": tip}
            if field.io_type in ("INT", "FLOAT"):
                args.update({k: v for k in ("min", "max", "step") if (v := getattr(field, k, None)) is not None})
            constructor = {"INT": io.Int, "FLOAT": io.Float, "BOOLEAN": io.Boolean, "STRING": io.String, "COMBO": io.String}[field.io_type]
            inputs.append(constructor.Input(key, **args))
        inputs.append(io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration(spec)),
                                      extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": spec}))
        schema.node_id = spec["nodeId"]
        schema.display_name = spec["title"]
        schema.inputs = inputs
        return schema

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, cls._panel_spec())
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def _panel_parameters(cls, configuration, inputs):
        spec = cls._panel_spec()
        params = validate_configuration(configuration, spec)
        for key in spec["layout"].get("overrides", []):
            value = _scalar(inputs.pop(key, None))
            if value is not None:
                params[key] = _validate_value(value, spec["fields"][key])
        return params

    @classmethod
    def execute(cls, configuration, **inputs):
        params = cls._panel_parameters(configuration, inputs)
        # List-input engines receive their usual one-element scalar
        # lists; image/mask/latent data and output list semantics stay intact.
        if cls.operation_schema().is_input_list:
            params = {key: [value] for key, value in params.items()}
        result = cls.execute_operation(**inputs, **params)
        report = LAYOUTS[cls.PANEL_KIND].get("result")
        if report and isinstance(result.result[report["index"]], str):
            result.ui = {**(result.ui or {}), "eclipse_operation_result": [result.result[report["index"]]]}
        return result


class FingerprintedOperationPanel(OperationPanel):
    @classmethod
    def fingerprint_inputs(cls, configuration, **inputs):
        params = cls._panel_parameters(configuration, inputs)
        return cls.fingerprint_operation(**inputs, **params)
