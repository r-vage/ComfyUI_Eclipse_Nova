# A native VIDEO loop accumulator retaining both decoded streams.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.video_clip_append import append_video_clip
from ..core.video_run import STORAGE_TYPE


class RvVideo_AppendClip(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Append Video Clip [Eclipse Nova]", display_name="Append Video Clip",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Trim decoded clip padding and append video plus audio. Optional Video Run Storage chooses CPU RAM, temporary disk or persistent output with restart recovery. Optional soundtrack replaces the assembled audio from time zero; without it, decoded clip audio is retained.",
            inputs=[io.Image.Input("images", tooltip="Decoded frames from this loop iteration."),
                    io.Int.Input("keep_frames", default=124, min=1, max=1000000,
                                 tooltip="Keep exactly this many frames from the start. Connect the clip conditioner's keep_frames output."),
                    io.Float.Input("fps", default=24, min=1, max=120, tooltip="H3 uses 24 FPS. This also determines each clip's exact audio duration."),
                    io.Audio.Input("audio", optional=True, tooltip="Decoded audio for this clip. Preserved in the assembled VIDEO when Save Video has no overriding soundtrack."),
                    io.Video.Input("previous", optional=True, tooltip="Previous loop VIDEO; leave disconnected at the first iteration."),
                    io.Audio.Input("soundtrack", optional=True, tooltip="Full selected soundtrack, starting at frame zero of the assembled video. Connect the clip planner's selected_audio. None keeps the generated audio. Save the VIDEO with Audio input disabled; its soundtrack is already selected."),
                    io.Custom(STORAGE_TYPE).Input("storage", optional=True, tooltip="Connect Video Run Storage to choose RAM, temporary files or persistent output with a reloadable manifest."),
                    io.Int.Input("generation_seed", optional=True, force_input=True, min=0, max=2**64-1,
                        tooltip="Exact seed used by RandomNoise for this part. Recorded in persistent run metadata without affecting conditioning.")],
            outputs=[io.Video.Output("video", tooltip="Accumulated clips with audio, suitable for loop state, Preview Video and Save Video Data."),
                     io.String.Output("run_path")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
        )

    @classmethod
    def execute(cls, images, keep_frames, fps, audio=None, previous=None, soundtrack=None, storage=None, generation_seed=None):
        metadata = {"workflow": (getattr(cls.hidden, "extra_pnginfo", None) or {}).get("workflow"),
                    "prompt": getattr(cls.hidden, "prompt", None)} if storage and storage.mode == "persistent" else None
        result = append_video_clip(images, keep_frames, fps, audio, previous, soundtrack, storage, metadata, generation_seed)
        run = getattr(result, "_eclipse_run_directory", None)
        return io.NodeOutput(result, f"{run}/run.json" if run else "")
