# Redesigned MiniMax interfaces share the existing planning and conditioning engines.
import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.frame_timeline import TIMELINE_TYPE
from ..core.minimax_h3_configuration import (
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
from ..core.minimax_h3_segment_plan import PLAN_KIND
from ..core.minimax_h3_segmented_conditioning import encode_segment
from ..core.minimax_h3_segmented_step import resolve_segment
from ..core.minimax_h3_segmented_timeline import plan_segments

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


def _schema(kind, inputs, outputs):
    title = TITLES[kind]
    return io.Schema(
        node_id=f"{title} [Eclipse Nova]", display_name=title,
        category=CATEGORY.MAIN.value + CATEGORY.MINIMAX.value,
        description="Themed MiniMax H3 panel. Connected controls override local settings. "
                    "Original audio, image ordering, plan types and output contracts are preserved.",
        is_input_list=kind in ("segmented_timeline", "segmented_conditioning"),
        inputs=[*inputs, *_overrides(kind), io.String.Input(
            "configuration", socketless=True, default=json.dumps(default_configuration(kind)),
            extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec(kind)})],
        outputs=outputs,
    )


class _MiniMaxPanel(io.ComfyNode):
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


class RvVideo_MiniMaxH3SegmentedTimelinePanel(_MiniMaxPanel):
    KIND = "segmented_timeline"

    @classmethod
    def define_schema(cls):
        return _schema(cls.KIND, [
            io.Audio.Input("audio", tooltip="Untouched master audio defines retained frames and the final mux."),
            io.Image.Input("image_batch", tooltip="Original timeline images. The transition frame belongs to its destination."),
            io.AudioEncoderOutput.Input("audio_encoder_output", optional=True, tooltip="Optional Wav2Vec activity features."),
            io.Audio.Input("conditioning_audio", optional=True, tooltip="Native-rate guide audio; use the same source in Plan Step."),
        ], [io.Custom(PLAN_KIND).Output("plan"), io.Int.Output("extension_task_count"), io.Int.Output("total_frames"),
            io.Int.Output("base_keep_frames"), io.String.Output("analysis_manifest"), io.String.Output("report")])


class RvVideo_MiniMaxH3SegmentedStepPanel(_MiniMaxPanel):
    KIND = "segmented_step"

    @classmethod
    def define_schema(cls):
        return _schema(cls.KIND, [
            io.Custom(PLAN_KIND).Input("plan"), io.Audio.Input("conditioning_audio", tooltip="Exactly the guide audio used by the planner."),
            io.Image.Input("image_batch"), io.Image.Input("previous_frames", optional=True),
            io.Custom(TIMELINE_TYPE).Input("timeline", optional=True, tooltip="Stored retained frames. Connect this or previous_frames; only requested continuity is read."),
        ], [io.Audio.Output("audio_slice"), io.Image.Output("continuity_clip"), io.Boolean.Output("has_continuity"),
            io.Image.Output("source_image"), io.Boolean.Output("has_start_guide"), io.Int.Output("start_guide_frame_index"),
            io.Image.Output("last_image"), io.Boolean.Output("has_last_image"), io.Int.Output("endpoint_frame_index"),
            io.Int.Output("render_frames"), io.Int.Output("crop_start_frames"), io.Int.Output("keep_frames"),
            io.Int.Output("prompt_index"), io.String.Output("conditioning_family"), io.String.Output("ref_image_size")])


class RvVideo_MiniMaxH3SegmentedConditioningPanel(_MiniMaxPanel):
    KIND = "segmented_conditioning"

    @classmethod
    def define_schema(cls):
        return _schema(cls.KIND, [
            io.Clip.Input("clip"), io.Vae.Input("vae"), io.Image.Input("source_image"), io.Image.Input("last_image", optional=True),
            io.Custom(PLAN_KIND).Input("segment_plan", optional=True, tooltip="Connect with task_index to apply planned camera-cut directions."),
            io.Int.Input("task_index", optional=True, force_input=True, min=0, max=65535,
                         tooltip="Current plan task; requires segment_plan. Separate from the prompt owner."),
        ], [io.Conditioning.Output("positive")])
