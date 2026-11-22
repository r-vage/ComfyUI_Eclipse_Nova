# Redesigned MiniMax interfaces share the existing planning and conditioning engines.
import json

from comfy_api.latest import io

from .keys import CATEGORY
from .minimax_h3_configuration import (
    CHOICES,
    INTEGER_FIELDS,
    NUMBERS,
    OVERRIDES,
    TIPS,
    TITLES,
    TOGGLES,
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    resolved_parameters,
    validate_configuration,
)
from .minimax_h3_segmented_conditioning import encode_segment
from .minimax_h3_segmented_step import resolve_segment
from .minimax_h3_segmented_timeline import plan_segments

ENGINES = {"segmented_timeline": plan_segments, "segmented_step": resolve_segment, "segmented_conditioning": encode_segment}


def _overrides(kind):
    fields = []
    for key in OVERRIDES[kind]:
        args = {"optional": True, "force_input": True,
                "tooltip": TIPS[key] + " Connected non-None values take priority over the panel."}
        if key in NUMBERS:
            field = NUMBERS[key]
            fields.append((io.Int if key in INTEGER_FIELDS else io.Float).Input(
                key, min=field["min"], max=field["max"], step=field["step"], **args))
        elif key in TOGGLES:
            fields.append(io.Boolean.Input(key, **args))
        else:
            fields.append(io.String.Input(key, **args))
    return fields


def panel_schema(kind, inputs, outputs, category=CATEGORY.MINIMAX):
    title = TITLES[kind]
    return io.Schema(
        node_id=f"{title} [Eclipse Nova]", display_name=title,
        category=CATEGORY.MAIN.value + category.value,
        description="Themed MiniMax H3 panel. Connected controls override local settings. "
                    "Original audio, image ordering, plan types and output contracts are preserved.",
        is_input_list=kind in ("segmented_timeline", "segmented_conditioning"),
        inputs=[*inputs, *_overrides(kind), io.String.Input(
            "configuration", socketless=True, default=json.dumps(default_configuration(kind)),
            extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec(kind)})],
        outputs=outputs,
    )


class MiniMaxPanel(io.ComfyNode):
    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration, cls.KIND)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, configuration, **inputs):
        overrides = {key: inputs.pop(key) for key in OVERRIDES[cls.KIND] if key in inputs}
        params = resolved_parameters(configuration, cls.KIND, **overrides)
        result = ENGINES[cls.KIND](**inputs, **params)
        values = result.result
        if cls.KIND == "segmented_timeline":
            report = values[-1]
        elif cls.KIND == "segmented_step":
            frames, crop, keep = values[9:12]
            report = f"Task {params['task_index']} · Render {frames} frames · Crop {crop} · Keep {keep}\nGenerated continuity: {'yes' if values[2] else 'no'}"
        else:
            report = f"Canvas: {params['width']} × {params['height']}"
            report += f"\nFamily: {CHOICES['conditioning_family'][params['conditioning_family']]} · Prompt index: {params['prompt_index']} · Visual strength: {params['visual_condition_strength']}"
        result.ui = {"eclipse_minimax_report": [report]}
        return result
