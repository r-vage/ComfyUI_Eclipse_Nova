# Saved render inputs and an Eclipse-owned video loop; sampling seed stays separate.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.image_helpers import unwrap_value
from ..core.loop import (
    STOP_CONTROL_TYPE,
    begin_loop,
    iteration_values,
    loop_outputs,
    missing_input,
)
from ..core.minimax_h3_clips import REFERENCE_MODES
from ..core.video_checkpoint import prepare_video_loop
from ..core.video_part_prompts import EDITS_TYPE
from ..core.video_resume import part_seed
from ..core.video_run import STORAGE_TYPE, VideoStorage

_CATEGORY = CATEGORY.MAIN.value + CATEGORY.VIDEO.value


class RvVideo_LoopStart(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Video Loop Start [Eclipse Nova]", display_name="Video Loop Start",
            category=_CATEGORY,
            description="Start or resume an H3 loop without Easy-Use. New runs snapshot resolved timings, prompts, references and audio before sampling. Resume restores those inputs and reuses completed parts in a new revision. Load mode blocks this loop without requesting generation inputs; route the loaded source directly to final output. Connect resolved outputs to conditioning and append; keep the Render Seed connected only to Video Part Seed.",
            inputs=[io.Custom(STORAGE_TYPE).Input("storage", tooltip="Operation and storage from Video Run Storage. Use this node's storage output for append nodes."),
                    io.Int.Input("restart_part", default=0, min=0, max=1000000, tooltip="Resume: 0 continues after completed parts. N retains parts 1 to N−1 and replaces N onward in a new revision. New run ignores this setting."),
                    io.Int.Input("parts_per_queue", default=0, min=0, max=1000000, tooltip="0 generates all remaining parts. 1 saves and previews one part, then returns a partial result for review. Resume on the next queue to continue."),
                    io.Combo.Input("reference_mode", options=list(REFERENCE_MODES), default="first_and_last", tooltip="Native H3 reference assignment for new runs. Resume restores the saved assignment."),
                    io.Float.Input("visual_condition_strength", default=0.999, min=0., max=1., optional=True, lazy=True, tooltip="Lip-sync reference strength for new runs; saved and restored on resume."),
                    io.AnyType.Input("plan", optional=True, lazy=True, tooltip="Resolved native clip plan or lip-sync audio plan. Requested only for a new run."),
                    io.AnyType.Input("previous", optional=True, lazy=True, tooltip="Source from Load Video Run. Requested only for resume."),
                    io.String.Input("run_path", optional=True, force_input=True, lazy=True, tooltip="Connect Load Video Run's run_path output. The dropdown remains the only run selection control."),
                    io.Int.Input("width", optional=True, force_input=True, lazy=True, tooltip="New-run canvas width. Resume uses the saved canvas."),
                    io.Int.Input("height", optional=True, force_input=True, lazy=True, tooltip="New-run canvas height. Resume uses the saved canvas."),
                    io.Image.Input("images", optional=True, lazy=True, tooltip="Resized reference images for the new run; stored with persistent checkpoints."),
                    io.Audio.Input("audio", optional=True, lazy=True, tooltip="Full master soundtrack for lip-sync. Native H3 uses its plan's selected audio."),
                    io.Audio.Input("conditioning_audio", optional=True, lazy=True, tooltip="Lip-sync guide/vocal audio, if different from the master soundtrack."),
                    io.AnyType.Input("prompts", optional=True, lazy=True, tooltip="Lip-sync prompt text/list, captured after analysis and manual routing."),
                    io.String.Input("first_part_prompt", optional=True, force_input=True, lazy=True, tooltip="Resolved first lip-sync shot prompt."),
                    io.Audio.Input("caption_audio", optional=True, lazy=True, tooltip="Full recording before selecting the H3 excerpt. Saved with the run for caption alignment after restarting. When absent, captions use the selected soundtrack from zero."),
                    io.Float.Input("caption_start", optional=True, force_input=True, lazy=True, default=0.0, min=0.0, tooltip="Start of the H3 excerpt in caption_audio. Resume restores the saved value, independently of the current source controls."),
                    io.Custom(STOP_CONTROL_TYPE).Input("stop_control", optional=True, tooltip="Optional Loop Control button, directly or through Get/Set. Put the control on the main canvas to stop after the current save and accumulated preview without opening this subgraph."),
                    io.Custom(EDITS_TYPE).Input("prompt_edits", optional=True, lazy=True, tooltip="Part Prompt Editor replacements for Resume only. Applied after restoring saved inputs and saved with the new revision. Restart at or before any changed completed part.")],
            outputs=loop_outputs(video=True), hidden=[io.Hidden.unique_id, io.Hidden.dynprompt], is_input_list=True)

    @classmethod
    def check_lazy_status(cls, storage, **kwargs):
        storage = unwrap_value(storage)
        if storage.run_mode == "Load saved run":
            return []
        requested = {"previous", "run_path", "prompt_edits"} if storage.run_mode == "Resume saved run" else {
            "plan", "width", "height", "images", "audio", "conditioning_audio", "prompts", "first_part_prompt", "visual_condition_strength", "caption_audio", "caption_start"}
        connected = cls.hidden.dynprompt.get_node(cls.hidden.unique_id).get("inputs", {})
        return [name for name in requested if name in connected and missing_input(kwargs.get(name))]

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        # A queue owns a fresh run/revision and stop token, independently of seed.
        return float("nan")

    @classmethod
    def execute(cls, storage, restart_part=0, parts_per_queue=0, reference_mode="first_and_last",
                visual_condition_strength=0.999, plan=None, previous=None, run_path=None, width=0, height=0,
                images=None, audio=None, conditioning_audio=None, prompts="", first_part_prompt="",
                caption_audio=None, caption_start=0.0, stop_control=None, prompt_edits=None):
        if unwrap_value(storage).run_mode == "Load saved run":
            from comfy_execution.graph_utils import ExecutionBlocker

            return io.NodeOutput(*(ExecutionBlocker(None) for _ in loop_outputs(video=True)))
        # Unwrap the executor envelope once, retaining a list of scene prompts.
        prompt_value = prompts[0] if isinstance(prompts, list) and len(prompts) == 1 else prompts
        data, previous, start, total, output_storage, report = prepare_video_loop(
            unwrap_value(storage) or VideoStorage(), unwrap_value(restart_part), unwrap_value(previous),
            unwrap_value(run_path), prompt_edits=unwrap_value(prompt_edits), plan=unwrap_value(plan), width=unwrap_value(width), height=unwrap_value(height),
            images=images, audio=unwrap_value(audio), conditioning_audio=unwrap_value(conditioning_audio),
            prompts=prompt_value or "", first_part_prompt=unwrap_value(first_part_prompt) or "",
            caption_audio=unwrap_value(caption_audio), caption_start=unwrap_value(caption_start),
            reference_mode=unwrap_value(reference_mode), visual_condition_strength=unwrap_value(visual_condition_strength))
        state = begin_loop(cls.hidden.unique_id, total, start, unwrap_value(parts_per_queue), [previous], data, output_storage, report,
                           stop_control=unwrap_value(stop_control))
        return io.NodeOutput(*iteration_values(state))


class RvVideo_PartSeed(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Video Part Seed [Eclipse Nova]", display_name="Video Part Seed", category=_CATEGORY,
            description="Compute the sampling seed independently of planning and conditioning. Change the connected Seed before queueing a resumed run to vary only the parts being rendered. A queued run uses a snapshot; editing the UI does not change a job already running.",
            inputs=[io.Int.Input("seed", force_input=True, min=0, max=2**64-1, tooltip="Base seed from Seed. Fixed repeats the seed schedule; randomize chooses a new base on the next queue."),
                    io.Int.Input("index", force_input=True, min=0, tooltip="Absolute index from Video Loop Start, including the retained prefix."),
                    io.Boolean.Input("increment", default=True, label_on="Different seed per part", label_off="Same seed per part",
                        tooltip="On adds the original zero-based part index to the base seed, wrapping at 64 bits. Native H3 previously used this schedule; off reproduces the previous lip-sync fixed-seed schedule.")],
            outputs=[io.Int.Output("seed", tooltip="Connect directly to RandomNoise and optionally the append node's generation_seed. Do not route it through a model loader, planner or conditioning node.")])

    @classmethod
    def execute(cls, seed, index, increment=True):
        return io.NodeOutput(part_seed(seed, index, increment))
