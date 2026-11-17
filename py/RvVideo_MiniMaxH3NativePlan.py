"""Video-only H3 planning with independent image descriptions and source clips."""
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_helpers import flatten_images, unwrap_value
from ..core.minimax_h3_clips import CLIP_PLAN_TYPE
from ..core.minimax_h3_native_plan import (
    add_source_boundaries,
    apply_native_scene_prompts,
    native_description_inputs,
    native_scene_prompts,
    plan_native_clips,
)
from ..core.scene_analysis import APPEARANCE_MODES, PLAN_TYPE

_CATEGORY = CATEGORY.MAIN.value + CATEGORY.MINIMAX.value


class RvVideo_MiniMaxH3ClipPlannerV2(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMax H3 Clip Planner_v2 [Eclipse Nova]", display_name="MiniMax H3 Clip Planner_v2",
            category=_CATEGORY, is_input_list=True,
            description="Native video generation: one image per source clip, cycling in loader order. Duration overrides each clip; zero uses video timing. Selected audio loops/trims to fit and is never a conditioning guide.",
            inputs=[
                io.Float.Input("duration", default=10, min=0, max=86400,
                               tooltip="Seconds per source clip or image. Zero uses loaded video durations; without video a positive value is required. Scene cuts scale with each clip."),
                io.Int.Input("max_clip_frames", default=362, min=124, max=362, step=17),
                io.String.Input("cut_times", default="", multiline=True,
                                tooltip="Scene cuts in seconds on the original merged video timeline. Source-clip boundaries are always retained."),
                io.String.Input("prompt", default="", multiline=True),
                io.String.Input("first_prompt", default="", multiline=True),
                io.String.Input("next_prompts", optional=True, force_input=True,
                                tooltip="Ordered subsequent scene prompts, preserving each multiline description."),
                io.Image.Input("images", optional=True),
                io.String.Input("image_prompts", optional=True, force_input=True,
                                tooltip="One independently generated description per enabled image, in loader order."),
                io.Audio.Input("audio", optional=True, tooltip="Selected excerpt. Loop this excerpt if short, trim if long; it never sets video duration."),
                io.Video.Input("reference_video", optional=True),
            ],
            outputs=[io.Custom(CLIP_PLAN_TYPE).Output("plan"), io.Int.Output("clip_count"),
                     io.Int.Output("total_frames"), io.Audio.Output("selected_audio"), io.String.Output("report"),
                     io.String.Output("prompts", is_output_list=True,
                                      tooltip="Exact combined generation text, once per logical scene. Connect to Prompt Review, then apply its output with H3 Reviewed Plan_v2.")])

    @classmethod
    def execute(cls, duration, max_clip_frames, cut_times, prompt, first_prompt,
                next_prompts=None, images=None, image_prompts=None, audio=None, reference_video=None):
        plan = plan_native_clips(unwrap_value(duration), unwrap_value(max_clip_frames),
                                 unwrap_value(cut_times), unwrap_value(prompt), unwrap_value(first_prompt),
                                 next_prompts, images, image_prompts, unwrap_value(audio), unwrap_value(reference_video))
        return io.NodeOutput(plan, len(plan.clips), plan.total_frames, plan.audio, plan.report, native_scene_prompts(plan))


class RvVideo_H3ReviewedPlanV2(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3 Reviewed Plan_v2 [Eclipse Nova]", display_name="H3 Reviewed Plan_v2", category=_CATEGORY,
            is_input_list=True,
            description="Use the final prompts displayed by Prompt Review for native generation. Retain source images, scene timing, soundtrack and technical splits. Does not write a prompt file.",
            inputs=[io.Custom(CLIP_PLAN_TYPE).Input("plan"),
                    io.String.Input("prompts", force_input=True,
                                    tooltip="Reviewed planner prompts: one entry per logical scene, preserving order.")],
            outputs=[io.Custom(CLIP_PLAN_TYPE).Output("plan")])

    @classmethod
    def execute(cls, plan, prompts):
        return io.NodeOutput(apply_native_scene_prompts(unwrap_value(plan), prompts))


class RvVideo_H3PromptPlanV2(RvVideo_MiniMaxH3ClipPlannerV2):
    @classmethod
    def define_schema(cls):
        schema = super().define_schema()
        schema.node_id = "H3 Prompt Plan_v2 [Eclipse Nova]"
        schema.display_name = "H3 Prompt Plan_v2"
        schema.description = "Plan timing and complete directions before optional LLM description. Multiple images use one clip each; a single image or text-only uses the first/next prompt list. Reviewed LLM results replace these directions through H3 Reviewed Plan_v2."
        schema.inputs = [field for field in schema.inputs if field.id != "image_prompts"]
        for field in schema.inputs:
            if field.id == "duration":
                field.tooltip = "Without video: seconds per clip; total duration is clip count × this value. With video: zero preserves source timing; positive overrides each source clip."
            elif field.id == "cut_times":
                field.tooltip = "Without video: one fewer cut than clips, in seconds from the video start; blank uses equal durations. With video: cuts on the loaded source timeline."
            elif field.id == "prompt":
                field.tooltip = "Global instructions included once in every scene's LLM input, or directly in generation when description is disabled."
        return schema

    @classmethod
    def execute(cls, duration, max_clip_frames, cut_times, prompt, first_prompt,
                next_prompts=None, images=None, audio=None, reference_video=None):
        plan = plan_native_clips(unwrap_value(duration), unwrap_value(max_clip_frames),
                                 unwrap_value(cut_times), unwrap_value(prompt), unwrap_value(first_prompt),
                                 next_prompts, images, audio=unwrap_value(audio),
                                 reference_video=unwrap_value(reference_video), prompt_timing=True)
        return io.NodeOutput(plan, len(plan.clips), plan.total_frames, plan.audio, plan.report, native_scene_prompts(plan))


class RvVideo_H3PromptInputsV2(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3 Prompt Inputs_v2 [Eclipse Nova]", display_name="H3 Prompt Inputs_v2", category=_CATEGORY,
            is_input_list=True,
            description="Send each planned scene's instructions to the LLM, paired with its assigned image when available. A single image is reused across its scenes; text-only needs no image. Technical render splits share one description.",
            inputs=[io.Custom(CLIP_PLAN_TYPE).Input("plan"), io.Image.Input("images", optional=True)],
            outputs=[io.Image.Output("images", is_output_list=True), io.String.Output("prompts", is_output_list=True)])

    @classmethod
    def execute(cls, plan, images=None):
        return io.NodeOutput(*native_description_inputs(unwrap_value(plan), images))


class RvVideo_H3ImageInputsV2(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3 Image Inputs_v2 [Eclipse Nova]", display_name="H3 Image Inputs_v2", category=_CATEGORY,
            is_input_list=True,
            inputs=[io.Boolean.Input("require_images", default=False,
                                     tooltip="Enable before image description to report missing images clearly."),
                    io.Image.Input("images", optional=True)],
            outputs=[io.Image.Output("images", is_output_list=True), io.Boolean.Output("has_images"),
                     io.Combo.Output("appearance_mode", options=list(APPEARANCE_MODES))])

    @classmethod
    def execute(cls, require_images=False, images=None):
        frames = flatten_images(images)
        if unwrap_value(require_images) and not frames:
            raise ValueError("Image description is enabled: load an image and enable the Images group.")
        return io.NodeOutput(frames, bool(frames), "exclude source appearance" if frames else "include source appearance")


class RvVideo_SceneSourceBoundariesV2(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Scene Source Boundaries_v2 [Eclipse Nova]", display_name="Scene Source Boundaries_v2",
            category=_CATEGORY,
            description="Keep every loaded clip boundary even when scene detection or cut limiting merges similar clips. Connect after Scene Cut Limit and before Scene Analysis Plan.",
            inputs=[io.Custom(PLAN_TYPE).Input("scene_plan"), io.Video.Input("video")],
            outputs=[io.Custom(PLAN_TYPE).Output("scene_plan")])

    @classmethod
    def execute(cls, scene_plan, video):
        return io.NodeOutput(add_source_boundaries(scene_plan, video))
