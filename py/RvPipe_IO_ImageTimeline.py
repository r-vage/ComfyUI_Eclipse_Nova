# Assemble inputs or unpack results for the pipe-only image timeline renderer.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_helpers import flatten_images
from ..core.image_timeline_pipe import assemble_pipe, fields
from ..core.image_timeline_video import single

_MISSING = object()


class RvPipe_IO_ImageTimeline(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        inputs, outputs = [io.Custom("PIPE").Input("pipe", optional=True)], [io.Custom("PIPE").Output("pipe")]
        for key, kind, tip in fields():
            value_type = getattr(io, kind)
            inputs.append(value_type.Input(key, optional=True, tooltip=tip,
                                           **({"force_input": True} if kind in ("String", "Int", "Float") else {}),
                                           **({"lazy": True} if key in ("audio_encoder_output", "analysis_audio") else {})))
            outputs.append(value_type.Output(key, **({"is_output_list": True} if key == "images" else {})))
        return io.Schema(
            node_id="IO Image Timeline [Eclipse Nova]", display_name="IO Image Timeline",
            category=CATEGORY.MAIN.value + CATEGORY.PIPE.value, is_input_list=True,
            description="Assemble or unpack Image Timeline Video's PIPE. Connected non-None inputs override inherited fields; empty text clears it. Load Image Timeline's PIPE carries its images and per-image crop/blend choices together. The same ordered images preserve those choices; replacement images clear them. The renderer supplies transition timing and defaults for inherited choices. A single image skips the optional analysis branches; for multiple images, connected encoder features take priority over analysis audio.",
            inputs=inputs, outputs=outputs,
        )

    @classmethod
    def check_lazy_status(cls, pipe=None, images=None, audio_encoder_output=_MISSING, analysis_audio=_MISSING, **_inputs):
        context = assemble_pipe(pipe, images=images)
        if len(flatten_images(context.get("images"))) < 2:
            return []
        if audio_encoder_output is not _MISSING:
            return ["audio_encoder_output"] if single(audio_encoder_output, "encoder output") is None else []
        if context.get("audio_encoder_output") is not None:
            return []
        return ["analysis_audio"] if analysis_audio is not _MISSING and single(analysis_audio, "analysis audio") is None else []

    @classmethod
    def execute(cls, pipe=None, **inputs):
        context = assemble_pipe(pipe, **inputs)
        outputs = [flatten_images(context.get(key)) or [None] if key == "images" else context.get(key)
                   for key, _kind, _tip in fields()]
        return io.NodeOutput(context, *outputs)
