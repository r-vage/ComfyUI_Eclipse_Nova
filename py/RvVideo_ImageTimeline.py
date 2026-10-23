# Build an audio-length video from ordered Image Selector results.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_blending import BLEND_MODES, BLEND_TOOLTIP
from ..core.image_effects import STYLE_MODES, STYLE_TOOLTIP
from ..core.image_timeline_pipe import render_pipe
from ..core.operation_panel import OperationPanel


class RvVideo_ImageTimeline(OperationPanel, io.ComfyNode):
    PANEL_KIND = "image_timeline"

    @classmethod
    def operation_schema(cls):
        return io.Schema(
            node_id="Image Timeline Video [Eclipse Nova]", display_name="Image Timeline Video",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Plan image changes and build a video before captions or saving. Connect IO Image Timeline's PIPE for images, audio and numeric overrides; use another IO node to unpack the result. One image holds for the audio duration. Multiple images use even spacing, quiet gaps or manual times, with optional blends around each cut. Frames stream to disk.",
            inputs=[
                io.Custom("PIPE").Input("pipe", tooltip="From IO Image Timeline. Non-None width, height, fps, duration and manual_transition_times fields override local values."),
                io.Combo.Input("mode", options=["Even", "Silence", "Manual"], default="Silence",
                    tooltip="Even divides the duration among images. Silence moves even targets to nearby quiet gaps, retaining targets when no gap qualifies. Manual uses exact switch times rounded to frames. One image ignores transitions."),
                io.Int.Input("width", default=0, min=0, max=8192,
                    tooltip="Output width. Both dimensions zero use the first image; one zero preserves its aspect ratio."),
                io.Int.Input("height", default=0, min=0, max=8192, tooltip="Output height. All images share the same output canvas."),
                io.Float.Input("fps", default=25.0, min=1.0, max=120.0, step=0.1,
                    tooltip="Output frames per second. Share the same value with Render Lyric Captions. The last frame covers the remainder of the audio."),
                io.Float.Input("duration", default=0.0, min=0.0, max=86400.0, step=0.1,
                    tooltip="Zero uses the full input audio; a positive value limits the video to that many seconds, never beyond the soundtrack."),
                io.Combo.Input("fit", options=["pad", "crop", "stretch"], default="pad",
                    tooltip="Pad preserves the full image with black borders. Crop fills the canvas from the center. Stretch changes the aspect ratio."),
                io.String.Input("manual_transition_times", default="",
                    tooltip="Comma-separated seconds from the start of the input audio. Supply one switch time per image after the first: e.g. 10, 22.5 for three images. Manual cuts must be increasing and inside the clip."),
                io.Combo.Input("transition_edge", options=["activity_resume", "silence_start"], default="activity_resume",
                    tooltip="Switch when sustained activity resumes after a quiet gap, or at the gap's start. Activity is not a speech classifier."),
                io.Float.Input("search_window_seconds", default=3.0, min=0.0, max=60.0, step=0.1,
                    tooltip="Seconds before and after each evenly spaced target to search for a quiet gap."),
                io.Float.Input("min_silence_duration", default=0.5, min=0.02, max=30.0, step=0.02,
                    tooltip="Minimum length of the low-activity gap. Longer values avoid switching during short pauses."),
                io.Float.Input("resume_hold_duration", default=0.2, min=0.02, max=30.0, step=0.02,
                    tooltip="Activity must resume for at least this duration to qualify the quiet gap."),
                io.Combo.Input("blend_mode", options=["cut", *BLEND_MODES], default="cut",
                    tooltip="Default for images without an explicit per-image blend. Load Image Timeline's Blend to next overrides this unless set to Use timeline setting. Cut keeps hard switches. " + BLEND_TOOLTIP),
                io.Float.Input("blend_duration", default=1.0, min=0.0, max=60.0, step=0.1,
                    tooltip="Default blend length in seconds for inherited blends; explicit per-image blends use their own Blend seconds. Centered around each planned cut. Zero keeps hard cuts. Short image intervals shorten the window so blends never overlap. Frame count, soundtrack and cut times stay unchanged."),
                io.Combo.Input("style", options=list(STYLE_MODES), default="off", tooltip=STYLE_TOOLTIP),
                io.Float.Input("style_strength", default=0.5, min=0.0, max=1.0, step=0.1,
                    tooltip="Strength across all images and transitions. Zero leaves colours and pixels unchanged."),
                io.Float.Input("style_period", default=2.0, min=0.2, max=60.0, step=0.1,
                    tooltip="Seconds for one repeating effect cycle. The clock continues across image changes. Constant colour grading ignores this value."),
            ],
            outputs=[io.Custom("PIPE").Output("pipe")],
        )

    @classmethod
    def execute_operation(cls, pipe, **settings):
        context = render_pipe(pipe, settings)
        return io.NodeOutput(context, ui={"eclipse_operation_result": [context["report"]]})
