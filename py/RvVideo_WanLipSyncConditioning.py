# Bounded-memory adapter around ComfyUI's native InfiniteTalk implementation.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.operation_panel import OperationPanel
from ..core.wan_motion_context import motion_context


class RvVideo_WanLipSyncConditioning(OperationPanel, io.ComfyNode):
    PANEL_KIND = "wan_conditioning"

    @classmethod
    def operation_schema(cls):
        return io.Schema(
            node_id="WAN LipSync Conditioning [Eclipse Nova]",
            display_name="WAN LipSync Conditioning",
            category=CATEGORY.MAIN.value + CATEGORY.VIDEO.value,
            description="Native InfiniteTalk with an explicit audio start frame. Accepts only the small motion tail from Plan Step; no accumulated image batch is needed in memory. Pair with its audio_start output at 25 FPS.",
            inputs=[
                io.Model.Input("model"), io.ModelPatch.Input("model_patch"),
                io.Conditioning.Input("positive"), io.Conditioning.Input("negative"),
                io.Vae.Input("vae"), io.AudioEncoderOutput.Input("audio_encoder_output_1"),
                io.Image.Input("start_image"), io.Image.Input("previous_frames"),
                io.Int.Input("audio_start", default=0, min=0, max=2147483647),
                io.Int.Input("width", default=832, min=16, max=16384, step=16),
                io.Int.Input("height", default=480, min=16, max=16384, step=16),
                io.Int.Input("length", default=81, min=5, max=4097, step=4),
                io.Int.Input("motion_frame_count", default=9, min=1, max=33),
                io.Float.Input("audio_scale", default=1.0, min=-10, max=10, step=0.1),
                io.ClipVisionOutput.Input("clip_vision_output", optional=True),
                io.AudioEncoderOutput.Input("audio_encoder_output_2", optional=True),
                io.Mask.Input("mask_1", optional=True), io.Mask.Input("mask_2", optional=True),
            ],
            outputs=[io.Model.Output("model"), io.Conditioning.Output("positive"),
                     io.Conditioning.Output("negative"), io.Latent.Output("latent"),
                     io.Int.Output("trim_image", tooltip="Native motion trim only. For warmup cropping use Plan Step trim_image.")],
        )

    @classmethod
    def execute_operation(cls, previous_frames, audio_start, motion_frame_count, **inputs):
        from comfy_extras.nodes_wan import WanInfiniteTalkToVideo

        mode = {"mode": "single_speaker"}
        if inputs.get("audio_encoder_output_2") is not None:
            mode = {"mode": "two_speakers", **{key: inputs.pop(key, None) for key in ("audio_encoder_output_2", "mask_1", "mask_2")}}
        context = motion_context(previous_frames, motion_frame_count, audio_start)
        return WanInfiniteTalkToVideo.execute(
            mode=mode, previous_frames=context, motion_frame_count=motion_frame_count, **inputs,
        )
