# A native VIDEO loop accumulator retaining both decoded streams on disk.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.video_clip_append import append_video_clip


class RvVideo_AppendClip(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Append Video Clip [Eclipse Nova]", display_name="Append Video Clip",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Trim decoded clip padding and append video plus audio to a temporary disk VIDEO. Loop state retains files instead of all decoded images. Optional soundtrack replaces the assembled audio from time zero; without it, decoded clip audio is retained. Files live while cached VIDEO outputs reference them.",
            inputs=[io.Image.Input("images", tooltip="Decoded frames from this loop iteration."),
                    io.Int.Input("keep_frames", default=124, min=1, max=1000000,
                                 tooltip="Keep exactly this many frames from the start. Connect the clip conditioner's keep_frames output."),
                    io.Float.Input("fps", default=24, min=1, max=120, tooltip="H3 uses 24 FPS. This also determines each clip's exact audio duration."),
                    io.Audio.Input("audio", optional=True, tooltip="Decoded audio for this clip. Preserved in the assembled VIDEO when Save Video has no overriding soundtrack."),
                    io.Video.Input("previous", optional=True, tooltip="Previous loop VIDEO; leave disconnected at the first iteration."),
                    io.Audio.Input("soundtrack", optional=True, tooltip="Full selected soundtrack, starting at frame zero of the assembled video. Connect the clip planner's selected_audio. None keeps the generated audio. Save the VIDEO with Audio input disabled; its soundtrack is already selected.")],
            outputs=[io.Video.Output("video", tooltip="Disk-backed clips with audio, suitable for loop state, Preview Video and Save Video Data.")],
        )

    @classmethod
    def execute(cls, images, keep_frames, fps, audio=None, previous=None, soundtrack=None):
        return io.NodeOutput(append_video_clip(images, keep_frames, fps, audio, previous, soundtrack))
