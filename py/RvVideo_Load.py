# Ordered native VIDEO loading with a single panel and explicit dimension/FPS inputs.

import json

from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_blending import BLEND_MODES, BLEND_TOOLTIPS
from ..core.image_effects import STYLE_MODES, STYLE_TOOLTIP
from ..core.video_helpers import preview_video_file
from ..core.video_loader import file_version, load_playlist, resolve_video_file
from ..core.video_panel_configuration import (
    EFFECT_DEFAULTS,
    LOAD_WIDGET,
    default_load,
    playlist_value,
    resolve_load,
    validate_load,
)


class RvVideo_Load(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Load Video [Eclipse Nova]", display_name="Load Video",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Trim and join an ordered video playlist with synchronized audio. Connected width, height and FPS override local values; Source timing retains every original frame duration.",
            inputs=[
                io.Int.Input("width", optional=True, force_input=True, min=0, max=16384,
                             tooltip="Override local width. Zero keeps automatic sizing from the first enabled clip."),
                io.Int.Input("height", optional=True, force_input=True, min=0, max=16384,
                             tooltip="Override local height. One zero dimension follows the first clip's aspect ratio."),
                io.Float.Input("fps", optional=True, force_input=True, min=1.0, max=240.0,
                               tooltip="Override local FPS in Fixed timing mode. Source timing keeps its original timestamps."),
                io.String.Input("configuration", socketless=True, default=json.dumps(default_load()),
                                extra_dict={"widgetType": LOAD_WIDGET, "editorSpec": {
                                    "kind": "load", "effect_defaults": EFFECT_DEFAULTS,
                                    "blend_modes": ["cut", *BLEND_MODES], "blend_tooltips": BLEND_TOOLTIPS,
                                    "style_modes": list(STYLE_MODES), "style_tooltip": STYLE_TOOLTIP}}),
            ],
            outputs=[io.Video.Output("video"), io.Custom("PIPE").Output("generation_data"),
                     io.Float.Output("duration"), io.String.Output("report")],
        )

    @classmethod
    def validate_inputs(cls, configuration, width=None, height=None, fps=None):
        try:
            config = validate_load(configuration)
            resolve_load(config, width, height, fps)
            if not any(row["enabled"] and row["file"] is not None for row in config["clips"]):
                return "Add and enable at least one video."
        except (TypeError, ValueError, OSError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        config = validate_load(configuration)
        return tuple((row["id"], file_version(resolve_video_file(row["file"])))
                     for row in config["clips"] if row["enabled"] and row["file"] is not None)

    @classmethod
    def execute(cls, configuration, width=None, height=None, fps=None):
        config = validate_load(configuration)
        result = load_playlist(playlist_value(config), **resolve_load(config, width, height, fps))
        return io.NodeOutput(*result, ui={"eclipse_video": [preview_video_file(result[0])[1]], "eclipse_report": [result[3]]})
