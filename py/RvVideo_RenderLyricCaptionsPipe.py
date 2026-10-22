# Pipe-only caption renderer with shared transcription and reference correction.
import json

from comfy_api.latest import io

from ..core import CATEGORY, lyric_captions
from ..core.lyric_caption_configuration import WIDGET_TYPE
from ..core.lyric_caption_pipe import (
    default_configuration,
    editor_spec,
    render_pipe,
    validate_configuration,
)
from ..core.lyric_reference import REFERENCE_REVISION


class RvVideo_RenderLyricCaptionsPipe(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Render Lyric Captions_v2 [Eclipse Nova]", display_name="Render Lyric Captions_v2",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Render lyrics from a PIPE assembled with IO Lyric Captions. Empty corrections use the original text/timing. Wording edits align within reference phrases; explicit corrected timing takes priority. Pipe dimensions, FPS, trim and seed override local controls; appearance and alignment choices stay local. Output carries the used lyrics/timing, video, SRT and report.",
            inputs=[io.Custom("PIPE").Input("pipe"),
                    io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration()),
                                    extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec()})],
            outputs=[io.Custom("PIPE").Output("pipe")],
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(configuration)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        config = validate_configuration(configuration)
        if config["seed"]["policy"] == "random":
            return float("nan")
        # Linked pipes are unresolved here. Model files need not exist for
        # reviewed timing; automatic paths verify their model at execution.
        return (lyric_captions.fingerprint_inputs(font_file=config["parameters"]["font_file"], corrected_timing=None),
                REFERENCE_REVISION)

    @classmethod
    def execute(cls, pipe, configuration):
        output = render_pipe(pipe, configuration)
        return io.NodeOutput(output, ui={"eclipse_seed": [str(output["seed"])]})
