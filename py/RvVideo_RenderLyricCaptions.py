# Caption panel with explicit dimension/FPS inputs and the shared rendering engine.
import json

from comfy_api.latest import io

from ..core import CATEGORY, lyric_captions
from ..core.frame_timeline import TIMELINE_TYPE
from ..core.lyric_caption_configuration import (
    WIDGET_TYPE,
    default_configuration,
    editor_spec,
    resolve_parameters,
    resolve_seed,
    validate_configuration,
)


class RvVideo_RenderLyricCaptions(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        background = io.MatchType.Template("background", allowed_types=[io.Image, io.Video, io.Custom(TIMELINE_TYPE)])
        return io.Schema(
            node_id="Render Lyric Captions [Eclipse Nova]", display_name="Render Lyric Captions",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Align full-song lyrics and render captioned video with the original soundtrack. Connected width, height and FPS override the panel. Review the result with Preview Video.",
            is_input_list=True,
            inputs=[
                io.Audio.Input("audio"),
                io.String.Input("lyrics", force_input=True, tooltip="Full-song plain lyrics or YuE2/MiniMax song JSON."),
                io.Float.Input("trim_start", force_input=True, min=0, max=86400, step=0.1,
                               tooltip="Trim audio and captions together, in seconds from the start of the full song."),
                io.Float.Input("duration", force_input=True, min=0, max=86400, step=0.1,
                               tooltip="Seconds to render. Zero uses the remainder of the song; clamped to available samples."),
                io.Audio.Input("vocals", optional=True, lazy=True,
                               tooltip="Full-song isolated vocals starting at zero, matching audio within 50 ms."),
                io.String.Input("corrected_timing", optional=True, force_input=True,
                                tooltip="Full-song timing JSON matching the cleaned lyrics bypasses alignment and lazy vocal separation. Blank or {} aligns the supplied lyrics automatically; {} passes through switches that skip empty strings."),
                io.MatchType.Input("background", template=background, optional=True, display_name="background image / video",
                                   tooltip="IMAGE batch/list, VIDEO or exact frame timeline. Background audio is ignored. Short backgrounds hold the last frame. Timelines require matching FPS."),
                io.Int.Input("width", optional=True, force_input=True, min=16, max=4096, step=2,
                             tooltip="Override panel width with an even pixel count. None keeps the local value."),
                io.Int.Input("height", optional=True, force_input=True, min=16, max=4096, step=2,
                             tooltip="Override panel height with an even pixel count. None keeps the local value."),
                io.Float.Input("fps", optional=True, force_input=True, min=1, max=120,
                               tooltip="Override panel FPS. None keeps the local value."),
                io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration()),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": editor_spec()}),
            ],
            outputs=[io.Video.Output("video"), io.String.Output("srt"), io.String.Output("report"),
                     io.String.Output("timing_json"), io.String.Output("cleaned_lyrics")],
        )

    @classmethod
    def validate_inputs(cls, configuration, width=None, height=None, fps=None):
        try:
            config = validate_configuration(lyric_captions._single(configuration, "configuration"))
            resolve_parameters(config, **{key: lyric_captions._single(value, key)
                                          for key, value in (("width", width), ("height", height), ("fps", fps))})
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, configuration, corrected_timing="", **_inputs):
        config = validate_configuration(lyric_captions._single(configuration, "configuration"))
        if config["seed"]["policy"] == "random":
            return float("nan")
        return lyric_captions.fingerprint_inputs(font_file=config["parameters"]["font_file"], corrected_timing=corrected_timing)

    @classmethod
    def check_lazy_status(cls, **inputs):
        return lyric_captions.check_lazy_status(**inputs)

    @classmethod
    def execute(cls, audio, lyrics, trim_start, duration, configuration,
                width=None, height=None, fps=None, **inputs):
        config = validate_configuration(lyric_captions._single(configuration, "configuration"))
        params = resolve_parameters(config, **{key: lyric_captions._single(value, key)
                                               for key, value in (("width", width), ("height", height), ("fps", fps))})
        seed = resolve_seed(config)
        result = lyric_captions.render_captions(audio, lyrics, trim_start, duration, **inputs, **params, seed=seed)
        return io.NodeOutput(*result, ui={"eclipse_seed": [str(seed)]})
