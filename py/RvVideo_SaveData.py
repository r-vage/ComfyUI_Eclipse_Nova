# One structured panel for IMAGE, native VIDEO and exact frame-timeline exports.

import json

import folder_paths
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.frame_timeline import TIMELINE_TYPE, timeline_input
from ..core.image_helpers import unwrap_value
from ..core.save_video_configuration import (
    FIELDS,
    WIDGET_TYPE,
    default_configuration,
    output_directory,
    pipe_options,
    validate_configuration,
)
from ..core.video_saving import (
    FilenameProcessor,
    VideoSaver,
    _placeholder_values,
    _unwrap_pipe,
    _video_input,
)
from ..core.video_timing import TIMING_TYPE


class RvVideo_SaveData(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        source = io.MatchType.Template("source", allowed_types=[io.Image, io.Video, io.Custom(TIMELINE_TYPE)])
        return io.Schema(
            node_id="Save Video Data [Eclipse Nova]",
            display_name="Save Video with Generation Data",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Save IMAGE frames, native VIDEO or an exact frame timeline as MP4/H.264. Includes audio, trim/loop controls, generation metadata and workflow JSON. Pipe FPS and filename/path values override local settings. VIDEO keeps its timing and soundtrack unless Audio input replaces the soundtrack with connected AUDIO.",
            inputs=[
                io.MatchType.Input("images", template=source, display_name="images / video"),
                io.String.Input("configuration", socketless=True, default=json.dumps(default_configuration()),
                                extra_dict={"widgetType": WIDGET_TYPE, "editorSpec": {"fields": FIELDS}}),
                io.Audio.Input("audio", optional=True, tooltip="Audio for IMAGE or frame timelines. Enable Audio input in the Mode bar to replace native VIDEO's soundtrack from time zero, preserving video duration. Short audio is padded with silence; long audio is trimmed."),
                io.Custom("PIPE").Input("pipe_opt", optional=True,
                                        tooltip="Generation metadata, fps, filename_prefix and output_path/path. Missing or None values use the panel."),
                io.Custom(TIMING_TYPE).Input("timing_opt", optional=True,
                                            tooltip="Source frame timing for IMAGE input; frame count and order must match. Overrides FPS and trim/loop. VIDEO already carries timing."),
            ],
            outputs=[io.MatchType.Output(source, id="images", display_name="images / video", is_output_list=True)],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            is_output_node=True,
            is_input_list=True,
        )

    @classmethod
    def validate_inputs(cls, configuration):
        try:
            validate_configuration(unwrap_value(configuration))
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, configuration, images, audio=None, pipe_opt=None, timing_opt=None):
        options = validate_configuration(unwrap_value(configuration))["options"]
        context = _unwrap_pipe(pipe_opt)
        has_timing = (_video_input(images) is not None or timeline_input(images) is not None
                      or unwrap_value(timing_opt, None) is not None)
        options = pipe_options(options, context, source_timing=has_timing)
        directory = output_directory(options.pop("output_path"), folder_paths.get_output_directory(),
                                     FilenameProcessor(_placeholder_values(context)))
        preview = options.pop("show_preview")
        return VideoSaver(cls.hidden, output_directory=directory, show_preview=preview).execute(
            images, audio=audio, pipe_opt=context, timing_opt=timing_opt, **options,
        )
