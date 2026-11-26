# Themed preview with IMAGE/VIDEO/timeline passthrough and a connected FPS override.

import json

from comfy_api.latest import Input, io

from ..core import CATEGORY
from ..core.cache_artifacts import artifact_fingerprint
from ..core.frame_timeline import TIMELINE_TYPE, FrameTimeline
from ..core.image_helpers import unwrap_value
from ..core.loop import missing_input
from ..core.resolution_sizing import require_number
from ..core.video_panel_configuration import (
    PREVIEW_FPS,
    PREVIEW_WIDGET,
    default_preview,
    validate_preview,
)
from ..core.video_preview import VideoPreview


class RvVideo_Preview(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        source = io.MatchType.Template("images_or_video", allowed_types=[io.Image, io.Video, io.Custom(TIMELINE_TYPE)])
        return io.Schema(
            node_id="Preview Video [Eclipse Nova]", display_name="Preview Video",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Resizable preview for IMAGE, VIDEO or exact frame timelines, with matching passthrough. VIDEO and timelines keep their timing. Stop reviews changed inputs; queue unchanged again to continue.",
            inputs=[
                io.MatchType.Input("images", template=source, display_name="images / video"),
                io.Audio.Input("audio", optional=True, tooltip="Audio for IMAGE or timelines; VIDEO retains its own soundtrack."),
                io.Float.Input("fps", optional=True, force_input=True, min=1.0, max=120.0,
                               tooltip="Override local FPS for IMAGE frames. VIDEO and timelines retain their source timing."),
                io.String.Input("configuration", socketless=True, default=json.dumps(default_preview()),
                                extra_dict={"widgetType": PREVIEW_WIDGET, "editorSpec": {"kind": "preview"}}),
                io.AnyType.Input("transition_plan", optional=True, lazy=True, tooltip="Preview picture transitions from a resolved video plan. The loop receives the original frames."),
            ],
            outputs=[io.MatchType.Output(source, id="images", display_name="images / video", is_output_list=True)],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo, io.Hidden.unique_id], is_output_node=True, is_input_list=True,
        )

    @classmethod
    def validate_inputs(cls, configuration, fps=None):
        try:
            validate_preview(unwrap_value(configuration))
            # ComfyUI supplies (None,) for unresolved links on list-input nodes.
            if isinstance(fps, tuple) and len(fps) == 1:
                fps = fps[0]
            value = unwrap_value(fps)
            if value is not None:
                require_number(value, PREVIEW_FPS)
        except (TypeError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def check_lazy_status(cls, images=None, **inputs):
        if (isinstance(unwrap_value(images), (Input.Video, FrameTimeline)) and "transition_plan" in inputs
                and missing_input(inputs["transition_plan"])):
            return ["transition_plan"]
        return []

    @classmethod
    def fingerprint_inputs(cls, configuration, **_inputs):
        validate_preview(unwrap_value(configuration))
        # ComfyUI already tracks connected media and settings. An unconditional
        # change here also invalidates downstream samplers and completed loops.
        return artifact_fingerprint()

    @classmethod
    def execute(cls, images, configuration, audio=None, fps=None, transition_plan=None):
        config = validate_preview(unwrap_value(configuration))
        rate = unwrap_value(fps)
        rate = config["fps"] if rate is None else require_number(rate, PREVIEW_FPS)
        return VideoPreview(cls.hidden).execute(images, rate, audio, config["stop"], transition_plan=unwrap_value(transition_plan))
