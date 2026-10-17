# Shared IMAGE, VIDEO and exact-timeline preview execution.

import json
import os
import random
import time
from fractions import Fraction

import av  # type: ignore
import folder_paths  # type: ignore
import torch  # type: ignore
from comfy.cli_args import args  # type: ignore
from comfy_api.latest import Input, io  # type: ignore

from .frame_timeline import raise_storage_error, timeline_input
from .image_helpers import (
    cat_and_fit_images,
    flatten_images,
    prepare_image_output,
    single_input_batch,
    unwrap_value,
    was_input_batch,
)
from .logger import log
from .video_helpers import preview_video_file

_LOG_PREFIX = "PreviewVideo"
_TEMP_DIR = folder_paths.get_temp_directory()
_PREFIX_APPEND = "_temp_" + "".join(
    random.choice("abcdefghijklmnopqrstupvxyz") for _ in range(5)
)


def _encode_video(
    images,
    fps: float,
    audio,
    output_path: str,
    codec: str = "h264",
    crf: int = 23,
    metadata=None,
) -> None:
    # Encode `images` (NHWC tensor in [0,1]) to mp4 at `output_path`.
    # Optionally muxes the provided AUDIO dict ({"waveform": Tensor[B,C,T], "sample_rate": int}).
    height = int(images.shape[-3])
    width = int(images.shape[-2])

    container = av.open(
        output_path, mode="w", options={"movflags": "use_metadata_tags+faststart"}
    )

    frames = iter(images)
    try:
        if metadata:
            for k, v in metadata.items():
                try:
                    container.metadata[k] = json.dumps(v) if not isinstance(v, str) else v
                except (TypeError, ValueError) as error:
                    log.debug(_LOG_PREFIX, f"Skipping unsupported metadata value: {type(error).__name__}")

        # Even dimensions are required by yuv420p; pad if necessary by cropping the encoder size.
        enc_w = width - (width % 2)
        enc_h = height - (height % 2)

        vstream = container.add_stream(codec, rate=Fraction(round(fps * 1000), 1000))
        if not isinstance(vstream, av.VideoStream):
            raise TypeError("Failed to create video stream")
        vstream.width = enc_w
        vstream.height = enc_h
        vstream.pix_fmt = "yuv420p"
        vstream.options = {"crf": str(crf), "preset": "veryfast"}

        astream = None
        if (
            audio is not None
            and isinstance(audio, dict)
            and "waveform" in audio
            and "sample_rate" in audio
        ):
            try:
                sample_rate = int(audio["sample_rate"])
                waveform = audio["waveform"]
                # waveform shape: [batch, channels, samples] — take batch 0
                if waveform.ndim == 3:
                    waveform = waveform[0]
                channels = int(waveform.shape[0])
                astream = container.add_stream("aac", rate=sample_rate)
                astream.layout = "stereo" if channels >= 2 else "mono"
            except Exception as e:  # noqa: BLE001 - optional preview soundtrack
                log.warning(_LOG_PREFIX, f"Audio stream init failed, skipping audio: {e}")
                astream = None

        # Encode video frames
        for frame in frames:
            arr = (
                torch.clamp(frame[..., :3] * 255.0, min=0, max=255)
                .to(device=torch.device("cpu"), dtype=torch.uint8)
                .numpy()
            )
            # Crop to even dims if needed
            if arr.shape[0] != enc_h or arr.shape[1] != enc_w:
                arr = arr[:enc_h, :enc_w, :]
            vframe = av.VideoFrame.from_ndarray(arr, format="rgb24")
            for packet in vstream.encode(vframe):
                container.mux(packet)
        for packet in vstream.encode():
            container.mux(packet)

        # Encode audio trimmed to video duration (num_frames / fps).
        if astream is not None:
            try:
                wf = audio["waveform"]
                if wf.ndim == 3:
                    wf = wf[0]
                sample_rate = int(audio["sample_rate"])
                num_frames = int(images.shape[0])
                max_samples = max(1, round(num_frames * sample_rate / fps))
                if wf.shape[-1] > max_samples:
                    wf = wf[..., :max_samples]
                # PyAV expects planar float32; shape [channels, samples]
                np_audio = (
                    wf.detach()
                    .to(device=torch.device("cpu"), dtype=torch.float32)
                    .contiguous()
                    .numpy()
                )
                aframe = av.AudioFrame.from_ndarray(
                    np_audio,
                    format="fltp",
                    layout="stereo" if np_audio.shape[0] >= 2 else "mono",
                )
                aframe.sample_rate = sample_rate
                for packet in astream.encode(aframe):
                    container.mux(packet)
                for packet in astream.encode():
                    container.mux(packet)
            except Exception as e:  # noqa: BLE001 - optional preview soundtrack
                log.warning(_LOG_PREFIX, f"Audio encode failed (video still saved): {e}")

    finally:
        if hasattr(frames, "close"):
            frames.close()
        container.close()


class VideoPreview:
    def __init__(self, hidden):
        self.hidden = hidden

    def execute(self, images, fps: float = 16.0, audio: dict | None = None, stop_review=False):
        fps = unwrap_value(fps, 16.0)
        audio = unwrap_value(audio, None)
        source = unwrap_value(images, None)
        timeline = timeline_input(images)
        video = source if isinstance(source, Input.Video) else None
        stop_review = unwrap_value(stop_review, False)
        if video is not None:
            if isinstance(images, (list, tuple)) and len(images) != 1:
                raise ValueError("Connect one VIDEO per input; combine multiple clips before this node.")
            # Audio is for the IMAGE fallback; VIDEO retains its own soundtrack.
            preview, descriptor = preview_video_file(video)
            if stop_review:
                import nodes
                nodes.interrupt_processing()
            return io.NodeOutput([preview], ui={"eclipse_video": [descriptor]})

        if images is None:
            return io.NodeOutput(None, ui={"eclipse_video": []})

        if timeline is not None:
            images_tensor = timeline
            fps = timeline.fps
            images_out = [timeline]
        else:
            flat_images = flatten_images(images)
            if not flat_images:
                return io.NodeOutput(None, ui={"eclipse_video": []})
            was_batch = was_input_batch(images)
            images_tensor = single_input_batch(images)
            if images_tensor is None:
                images_tensor = cat_and_fit_images(flat_images, log_prefix=_LOG_PREFIX)
            images_out = prepare_image_output(images_tensor, was_batch)
        if images_tensor is None:
            return io.NodeOutput(None, ui={"eclipse_video": []})

        height = int(images_tensor.shape[-3])
        width = int(images_tensor.shape[-2])

        filename_prefix = "EclipseVideo" + _PREFIX_APPEND
        full_output_folder, filename, counter, subfolder, _ = (
            folder_paths.get_save_image_path(filename_prefix, _TEMP_DIR, width, height)
        )

        # Timestamp guarantees unique URL per execution (cache-busting for <video>).
        timestamp = int(time.time() * 1000) % 100000000
        file = f"{filename}_{counter:05}_{timestamp}_.mp4"
        out_path = os.path.join(full_output_folder, file)

        metadata = None
        if not args.disable_metadata:
            metadata = {}
            if self.hidden.extra_pnginfo is not None:
                extra_png = self.hidden.extra_pnginfo
                if isinstance(extra_png, list) and len(extra_png) > 0:
                    extra_png = extra_png[0]
                if isinstance(extra_png, dict):
                    metadata.update(extra_png)
            if self.hidden.prompt is not None:
                p_info = self.hidden.prompt
                if isinstance(p_info, list) and len(p_info) > 0:
                    p_info = p_info[0]
                metadata["prompt"] = p_info

        try:
            _encode_video(images_tensor, fps, audio, out_path, metadata=metadata)
        except Exception as e:
            if timeline is not None:
                if os.path.exists(out_path):
                    os.unlink(out_path)
                raise_storage_error(e, _TEMP_DIR)
                raise
            log.error(_LOG_PREFIX, f"Failed to encode preview video: {e}")
            return io.NodeOutput(images_out, ui={"eclipse_video": []})

        result = {
            "filename": file,
            "subfolder": subfolder,
            "type": "temp",
            "format": "video/mp4",
            "frame_rate": fps,
        }
        # Custom ui key — frontend skips native fixed-size preview; the JS
        # extension renders a resizable DOM <video> instead.
        if stop_review:
            import nodes
            nodes.interrupt_processing()
        return io.NodeOutput(images_out, ui={"eclipse_video": [result]})
