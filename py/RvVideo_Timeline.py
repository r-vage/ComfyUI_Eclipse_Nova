"""Plan, review and dispatch a single disk-backed video render loop."""
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_helpers import flatten_images, unwrap_value
from ..core.loop import missing_input
from ..core.minimax_h3_clips import CLIP_PLAN_TYPE, clip_at, clip_conditioning
from ..core.minimax_h3_prompts import segment_prompt
from ..core.video_scene_transitions import TRANSITIONS_TYPE
from ..core.video_timeline import (
    DURATIONS,
    GUIDES,
    IMAGE_ASSIGNMENTS,
    MODELS,
    SHOT_MODES,
    TIMELINE_TYPE,
    model_path,
    plan_timeline,
)
from ..core.wan_timeline import WAN_KIND, resolve_wan_part, wan_parts

_CATEGORY = CATEGORY.MAIN.value + CATEGORY.VIDEO.value


class RvVideo_TimelineAudio(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Video Timeline Audio [Eclipse Nova]", display_name="Video Timeline Audio",
            category=_CATEGORY, inputs=[io.Combo.Input("source", options=[
                "Recording or video", "Recording", "Reference video", "Isolated vocals", "None"]),
                io.Audio.Input("recording", optional=True, lazy=True), io.Video.Input("video", optional=True, lazy=True),
                io.Audio.Input("vocals", optional=True, lazy=True)], outputs=[io.Audio.Output("audio")],
                hidden=[io.Hidden.dynprompt, io.Hidden.unique_id])

    @classmethod
    def check_lazy_status(cls, source, **values):
        fields = {"Recording or video": ("recording", "video"), "Recording": ("recording",),
                  "Reference video": ("video",), "Isolated vocals": ("vocals",), "None": ()}
        connected = cls.hidden.dynprompt.get_node(cls.hidden.unique_id)["inputs"]
        return [key for key in fields[source] if key in connected and values.get(key) is None]

    @classmethod
    def execute(cls, source, recording=None, video=None, vocals=None):
        if source in ("Recording or video", "Recording") and recording is not None:
            return io.NodeOutput(recording)
        if source in ("Recording or video", "Reference video") and video is not None:
            from ..core.video_stream import video_frame_source

            track = video_frame_source(video)
            if track.has_audio and getattr(video, "eclipse_source_has_audio", True):
                return io.NodeOutput(track.audio())
        return io.NodeOutput(vocals if source == "Isolated vocals" else None)


class RvVideo_TimelinePlanner(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Video Timeline Planner [Eclipse Nova]", display_name="Video Timeline Planner",
            category=_CATEGORY, is_input_list=True,
            inputs=[io.Combo.Input("model", options=list(MODELS)), io.Combo.Input("duration_source", options=list(DURATIONS)),
                    io.Float.Input("seconds", default=5, min=-1, max=86400, step=0.1,
                                   tooltip="With reference video, keep up to this many seconds per clip or in total. Use −1 for the available footage."),
                    io.Combo.Input("guidance", options=list(GUIDES),
                                   tooltip="H3 uses the scene image as its first frame, first and last keyframes, or an active reference. WAN uses one reference per scene."),
                    io.Int.Input("h3_capacity", default=362, min=124, max=362, step=17),
                    io.Int.Input("wan_context", default=81, min=5, max=4097, step=4),
                    io.Int.Input("wan_overlap", default=9, min=1, max=33),
                    io.Float.Input("opening_warmup", default=0., min=0., max=10., step=.1, tooltip="Hidden opening frames for H3 FL guidance, in seconds."),
                    io.Float.Input("warmup", default=0., min=0., max=10., step=.1),
                    io.Int.Input("skip_tail_frames", default=0, min=0, max=4096,
                                 tooltip="Skip a final technical continuation retaining at most this many visible frames. Zero preserves full duration."),
                    io.String.Input("global_prompt", default="", multiline=True),
                    io.String.Input("scene_prompts", optional=True, force_input=True),
                    io.String.Input("cut_times", default="", tooltip="Comma-separated cut times in source seconds when using video, otherwise in output seconds."),
                    io.Video.Input("reference_video", optional=True), io.Image.Input("images", optional=True),
                    io.Audio.Input("timing_audio", optional=True, lazy=True, tooltip="Duration for Audio track length."),
                    io.Audio.Input("conditioning_audio", optional=True, lazy=True, tooltip="Vocal guide for lip-sync. Excess is trimmed and missing time padded with silence."),
                    io.Audio.Input("soundtrack", optional=True, tooltip="Final recording. A short excerpt repeats to fit. Native H3 generates sound when disconnected."),
                    io.String.Input("analysis_opening", optional=True, force_input=True,
                                    tooltip="Separate first direction from Scene Analysis to H3. A Wildcard Processor list already begins at scene 1."),
                    io.Combo.Input("image_assignment", optional=True, options=list(IMAGE_ASSIGNMENTS), default=IMAGE_ASSIGNMENTS[0],
                                   tooltip="Keep one image per source clip, advance once per cut and hold the last, cycle, or distribute images over time using the nearest existing cuts. H3 First and last pairs consecutive scene images."),
                    io.Combo.Input("shot_mode", display_name="H3 shot mode", optional=True, options=list(SHOT_MODES), default=SHOT_MODES[0],
                                   tooltip="Separate at cuts starts a render at each cut. Group timed shots fits up to 15 visible seconds into one H3 prompt, within the selected render capacity. Image changes and playlist joins start a new group. H3 interprets internal cut times. WAN uses its own transitions."),
                    io.Custom(TRANSITIONS_TYPE).Input("transitions", optional=True, tooltip="Optional outgoing shot, prompt and picture settings from Video Transition to Next.")],
            outputs=[io.Custom(TIMELINE_TYPE).Output("timeline"), io.String.Output("scene_prompts", is_output_list=True,
                         tooltip="Initial generation text per scene or H3 shot group, in review order."),
                     io.Image.Output("scene_images", is_output_list=True, tooltip="One assigned image per original shot, paired with description_prompts."), io.String.Output("report"),
                     io.Int.Output("total_frames"), io.Float.Output("fps"), io.Float.Output("duration"),
                     io.String.Output("model_family", tooltip="Selected render family for shared model settings."),
                     io.String.Output("description_prompts", is_output_list=True,
                                      tooltip="Scene-only requests for the optional prompt writer. Global direction is applied at final prompt review.")],
            hidden=[io.Hidden.dynprompt, io.Hidden.unique_id])

    @classmethod
    def check_lazy_status(cls, model, duration_source, timing_audio=None, conditioning_audio=None, **_):
        requested = []
        # ComfyUI passes (None,) for a pending link on a list-input node.
        if unwrap_value(duration_source) == DURATIONS[1] and missing_input(timing_audio):
            requested.append("timing_audio")
        if unwrap_value(model) != MODELS[0] and missing_input(conditioning_audio):
            requested.append("conditioning_audio")
        connected = cls.hidden.dynprompt.get_node(cls.hidden.unique_id)["inputs"]
        return [name for name in requested if name in connected]

    @classmethod
    def execute(cls, scene_prompts=None, images=None, analysis_opening=None, **inputs):
        opening = unwrap_value(analysis_opening)
        directions = ([opening] if opening else []) + list(scene_prompts or ())
        timeline = plan_timeline(**{k: unwrap_value(v) for k, v in inputs.items()},
                                 scene_prompts=directions, images=images)
        plan = timeline.plan
        family = model_path(plan)
        frames = flatten_images(images)
        total, fps = (plan.total_frames, 24) if family == MODELS[0] else (plan["total_frames"], plan["fps"])
        # A blank request activates SmartLLM's original-story mode. When the user
        # supplied only global direction, ask for composition without exposing it.
        composition = "Describe only the starting composition supported by the available reference."
        shots = timeline.description_scenes
        descriptions = [s.direction or (composition if timeline.global_prompt.strip() else "") for s in shots]
        return io.NodeOutput(timeline, [s.prompt for s in timeline.scenes],
                             [frames[s.image] for s in shots if s.image is not None],
                             timeline.report, total, float(fps), total / fps, family, descriptions)


class RvVideo_TimelineGenerationPrompts(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Video Timeline Generation Prompts [Eclipse Nova]", display_name="Video Timeline Generation Prompts",
            category=_CATEGORY, is_input_list=True,
            inputs=[io.Custom(TIMELINE_TYPE).Input("timeline"), io.String.Input("descriptions", optional=True, force_input=True,
                    tooltip="Optional scene descriptions from the prompt writer. Without this input the timeline uses its original scene directions.")],
            outputs=[io.String.Output("prompts", is_output_list=True)],
            description="Apply global direction after scene description. In grouped H3 mode, combine shot descriptions and timed cuts into one editable prompt per group. H3 lip-sync uses the supplied audio and starts each soundscape at N/A.")

    @classmethod
    def execute(cls, timeline, descriptions=None):
        return io.NodeOutput(unwrap_value(timeline).generation_prompts(descriptions))


class RvVideo_TimelineIO(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Video Timeline I/O [Eclipse Nova]", display_name="Video Timeline I/O",
            category=_CATEGORY, is_input_list=True,
            inputs=[io.Custom(TIMELINE_TYPE).Input("timeline"), io.String.Input("reviewed_prompts", force_input=True),
                    io.AnyType.Input("timing_review", optional=True,
                                     tooltip="Wait for the enabled transcript timing preview before starting a new run.")],
            outputs=[io.Custom(TIMELINE_TYPE).Output("timeline"), io.Audio.Output("soundtrack"),
                     io.Audio.Output("conditioning_audio")])

    @classmethod
    def execute(cls, timeline, reviewed_prompts, timing_review=None):
        reviewed = unwrap_value(timeline).reviewed(reviewed_prompts)
        return io.NodeOutput(reviewed, reviewed.soundtrack, reviewed.guide)


class RvVideo_TimelineSelect(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Video Timeline Select [Eclipse Nova]", display_name="Video Timeline Select",
            category=_CATEGORY, description="Request only the branch selected by the current or restored render plan.",
            inputs=[io.AnyType.Input("plan", tooltip="Resolved render plan or model_family from Video Timeline Planner or Load Video Run."), *[io.AnyType.Input(k, optional=True, lazy=True)
                                               for k in ("native", "segmented", "wan")]],
            outputs=[io.AnyType.Output("value")], hidden=[io.Hidden.dynprompt, io.Hidden.unique_id])

    @classmethod
    def check_lazy_status(cls, plan, **values):
        key = ("native", "segmented", "wan")[MODELS.index(model_path(plan))]
        connected = cls.hidden.dynprompt.get_node(cls.hidden.unique_id)["inputs"]
        if key not in connected:
            raise ValueError(f"Connect or enable the {model_path(plan)} input of Video Timeline Select.")
        return [key] if values.get(key) is None else []

    @classmethod
    def execute(cls, plan, native=None, segmented=None, wan=None):
        return io.NodeOutput((native, segmented, wan)[MODELS.index(model_path(plan))])


class RvVideo_TimelineNativeConditioning(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Video Timeline Native Conditioning [Eclipse Nova]",
            display_name="Video Timeline Native Conditioning", category=_CATEGORY,
            inputs=[io.Custom(CLIP_PLAN_TYPE).Input("plan"), io.Int.Input("index", force_input=True),
                    io.Clip.Input("clip"), io.Vae.Input("vae"), io.Int.Input("width", force_input=True),
                    io.Int.Input("height", force_input=True), io.Image.Input("images", optional=True),
                    io.Video.Input("previous", optional=True), io.Vae.Input("audio_vae", optional=True),
                    io.AnyType.Input("reference_mode", optional=True)],
            outputs=[io.Conditioning.Output("positive"), io.Latent.Output("latent"),
                     io.Int.Output("keep_frames"), io.Int.Output("crop_start")])

    @classmethod
    def execute(cls, plan, index, clip, vae, width, height, images=None, previous=None,
                audio_vae=None, reference_mode="first_and_last"):
        positive, latent, keep, _ = clip_conditioning(plan, index, clip, vae, width, height, 0,
                                                     reference_mode, images, audio_vae, previous)
        return io.NodeOutput(positive, latent, keep, clip_at(plan, index).crop_start)


class RvVideo_TimelineWanStep(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Video Timeline WAN Step [Eclipse Nova]", display_name="Video Timeline WAN Step",
            category=_CATEGORY,
            inputs=[io.Custom(WAN_KIND).Input("plan"), io.Int.Input("index", force_input=True),
                    io.Image.Input("images"), io.AnyType.Input("previous", optional=True),
                    io.Combo.Input("blend_mode", options=["linear", "pyramid"])],
            outputs=[io.Image.Output("start_image"), io.Image.Output("motion_tail"), io.Int.Output("keep_frames"),
                     io.Int.Output("crop_start"), io.Int.Output("audio_start"), io.Int.Output("context_length"),
                     io.Int.Output("motion_frame_count"), io.String.Output("prompt")])

    @classmethod
    def execute(cls, plan, index, images, previous=None, blend_mode="linear"):
        step = resolve_wan_part(plan, index, images, previous, blend_mode)
        part = wan_parts(plan)[index]
        return io.NodeOutput(*step, plan["context_length"], plan["overlap_frames"],
                             segment_prompt("", part["image_index"], plan=plan, task=part))
