# Assemble or unpack lyric-caption media, timing, dimensions and seed.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.frame_timeline import TIMELINE_TYPE
from ..core.lyric_caption_pipe import assemble_pipe, fields


class RvPipe_IO_LyricCaptions(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        background = io.MatchType.Template("background", allowed_types=[io.Image, io.Video, io.Custom(TIMELINE_TYPE)])
        inputs, outputs = [io.Custom("PIPE").Input("pipe", optional=True)], [io.Custom("PIPE").Output("pipe")]
        for key, kind, tooltip in fields():
            if kind == "Background":
                inputs.append(io.MatchType.Input(key, template=background, optional=True, tooltip=tooltip))
                outputs.append(io.MatchType.Output(background, id=key))
                continue
            value_type = getattr(io, kind)
            inputs.append(value_type.Input(key, optional=True, tooltip=tooltip,
                                           **({"force_input": True} if kind in ("String", "Int", "Float", "Boolean") else {})))
            outputs.append(value_type.Output(key))
        return io.Schema(
            node_id="IO Lyric Captions [Eclipse Nova]", display_name="IO Lyric Captions",
            category=CATEGORY.MAIN.value + CATEGORY.PIPE.value, is_input_list=True,
            description="Assemble or unpack a lyric PIPE. Connected non-None values override inherited fields; empty correction strings clear them. Dimensions, FPS, trim and seed can override the renderer; appearance and alignment choices stay in its panel. Other pipe data is retained. Use before and after Render Lyric Captions_v2.",
            inputs=inputs, outputs=outputs,
        )

    @classmethod
    def execute(cls, pipe=None, **inputs):
        context = assemble_pipe(pipe, **inputs)
        return io.NodeOutput(context, *(context.get(key) for key, _kind, _tip in fields()))
