# Optional-audio native H3 clip planning and conditioning.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.minimax_h3_clips import (
    CLIP_PLAN_TYPE,
    REFERENCE_MODES,
    clip_conditioning,
    plan_clips,
)

_CATEGORY = CATEGORY.MAIN.value + CATEGORY.MINIMAX.value


class RvVideo_MiniMaxH3ClipPlanner(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMax H3 Clip Planner [Eclipse Nova]", display_name="MiniMax H3 Clip Planner",
            category=_CATEGORY,
            description="Plan native H3 T2VA/first-last-image clips at 24 FPS. Audio priority: loaded audio, reference video audio, H3-generated audio. A silent reference still supplies duration. No lip-sync audio encoder is used.",
            inputs=[
                io.Float.Input("duration", default=15, min=1/24, max=86400,
                               tooltip="Total seconds when neither loaded audio nor a reference video supplies duration. Increase this to generate several clips."),
                io.Int.Input("max_clip_frames", default=362, min=124, max=362, step=17,
                             tooltip="Maximum frames per H3 invocation. Long parts split automatically; short clips render at least 124 frames and discard padding. Lower values reduce peak memory."),
                io.String.Input("cut_times", default="", multiline=True,
                                tooltip="Comma-separated cut positions in seconds, measured from the selected source's start. Blank distributes supplied scene prompts evenly across the duration; a single prompt uses only maximum-length splits. Cuts beyond duration are ignored."),
                io.String.Input("prompt", default="", multiline=True,
                                tooltip="Global direction used in every clip, including sound when H3 generates audio."),
                io.String.Input("first_prompt", default="", multiline=True,
                                tooltip="Opening part only. Describe its starting pose and visible action; timing belongs in cut_times."),
                io.String.Input("next_prompts", default="", multiline=True,
                                tooltip="One subsequent scene prompt per line. With cut times, prompts follow those scenes; without times, first_prompt plus these lines share the duration evenly. Long scenes retain their prompt across capacity splits. Missing prompts use global direction alone."),
                io.Audio.Input("audio", optional=True, tooltip="Highest-priority soundtrack; supplies duration and guides generation. Save using selected_audio to retain this exact recording."),
                io.Video.Input("reference_video", optional=True, tooltip="Second-priority audio and timing source. Use the same trimmed VIDEO for scene analysis. A silent/muted video retains its duration and lets H3 generate audio."),
            ],
            outputs=[io.Custom(CLIP_PLAN_TYPE).Output("plan"), io.Int.Output("clip_count"),
                     io.Int.Output("total_frames"), io.Audio.Output("selected_audio", tooltip="Original loaded/reference audio, or None when H3 generates audio."),
                     io.String.Output("report")],
        )

    @classmethod
    def execute(cls, duration, max_clip_frames, cut_times, prompt, first_prompt, next_prompts,
                audio=None, reference_video=None):
        plan = plan_clips(duration, max_clip_frames, cut_times, prompt, first_prompt, next_prompts, audio, reference_video)
        return io.NodeOutput(plan, len(plan.clips), plan.total_frames, plan.audio, plan.report)


class RvVideo_MiniMaxH3ClipConditioning(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMax H3 Clip Conditioning [Eclipse Nova]", display_name="MiniMax H3 Clip Conditioning",
            category=_CATEGORY,
            description="Use native H3 text, visual-reference or first/last-image conditioning for one planned clip, with optional AddGuide audio. Keeps the last-image guide at the retained endpoint when H3 pads a short clip. No images gives text-to-video-and-audio.",
            inputs=[io.Custom(CLIP_PLAN_TYPE).Input("plan"),
                    io.Int.Input("index", default=0, min=0, tooltip="Connect the zero-based for-loop index."),
                    io.Clip.Input("clip"), io.Vae.Input("vae"),
                    io.Int.Input("width", default=1344, min=32, max=8192, step=32),
                    io.Int.Input("height", default=768, min=32, max=8192, step=32),
                    io.Int.Input("seed", default=0, min=0, max=2**64-1, tooltip="Base seed; each clip adds its loop index."),
                    io.Combo.Input("reference_mode", options=list(REFERENCE_MODES), default=REFERENCE_MODES[0],
                                   tooltip="first_and_last reuses the first/last images for every clip; one image anchors only the start. first_only/last_only use one endpoint. first_per_scene uses image 1 for scene 1, image 2 for scene 2, then holds the final image; capacity splits keep the same scene image. adjacent_pairs uses images 1→2, 2→3 per scene, then holds the final image. reference_images uses up to 9 images as native visual references without fixing endpoints; <Picture 1>, etc. can identify them in the prompt. text_only ignores images."),
                    io.Image.Input("images", optional=True, tooltip="Connect Load Image Timeline's resized IMAGE output. Mute that input group or select text_only for T2VA. Slot fades do not blend the generated clips."),
                    io.Vae.Input("audio_vae", optional=True, tooltip="Required with an external/reference soundtrack. The native audio VAE encodes each clip's guide; it also decodes generated audio downstream.")],
            outputs=[io.Conditioning.Output("positive"), io.Latent.Output("latent"),
                     io.Int.Output("keep_frames"), io.Int.Output("seed")],
        )

    @classmethod
    def execute(cls, plan, index, clip, vae, width, height, seed,
                reference_mode=REFERENCE_MODES[0], images=None, audio_vae=None):
        return io.NodeOutput(*clip_conditioning(plan, index, clip, vae, width, height, seed,
                                               reference_mode, images, audio_vae))
