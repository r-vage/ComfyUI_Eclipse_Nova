# Keep generated video and audio together in files or CPU RAM between iterations.
import os
import tempfile
from fractions import Fraction
from pathlib import Path

import folder_paths
import torch
from comfy_api.latest import Input, InputImpl, VideoComponents

from .video_helpers import TemporaryVideo
from .video_run import create_run_directory, save_run
from .video_timing import VideoTiming, encode_timed_video


class MemoryClipVideo(Input.Video):
    def __init__(self, chunks, fps, soundtrack=None):
        self.chunks = chunks
        self.fps = fps
        self.soundtrack = soundtrack

    def get_dimensions(self):
        return self.chunks[0][0].shape[2], self.chunks[0][0].shape[1]

    def get_frame_count(self):
        return sum(len(images) for images, _ in self.chunks)

    def get_frame_rate(self):
        return Fraction(str(self.fps))

    def get_audio(self):
        audio = self.soundtrack
        if audio is None:
            provided = [a for _, a in self.chunks if a is not None]
            if provided:
                rate = int(provided[0]["sample_rate"])
                channels = provided[0]["waveform"].shape[1]
                parts = []
                for images, part in self.chunks:
                    count = round(len(images) / self.fps * rate)
                    samples = torch.zeros(1, channels, count)
                    if part is not None:
                        if int(part["sample_rate"]) != rate or part["waveform"].shape[1] != channels:
                            raise ValueError("Memory clips must use the same audio sample rate and channels.")
                        end = min(count, part["waveform"].shape[-1])
                        samples[..., :end] = part["waveform"][..., :end].detach().cpu()
                    parts.append(samples)
                audio = {"waveform": torch.cat(parts, dim=-1), "sample_rate": rate}
        if audio is not None:
            count = round(self.get_frame_count() / self.fps * audio["sample_rate"])
            audio = {**audio, "waveform": audio["waveform"][..., :count]}
        return audio

    def get_components(self):
        return VideoComponents(images=torch.cat([images for images, _ in self.chunks]),
                               frame_rate=self.get_frame_rate(), audio=self.get_audio())

    def save_to(self, path, **kwargs):
        return InputImpl.VideoFromComponents(self.get_components()).save_to(path, **kwargs)

    def as_trimmed(self, start_time=None, duration=None, strict_duration=False):
        total = self.get_frame_count() / self.fps
        start = float(start_time or 0)
        if start < 0:
            start = max(0, total + start)
        available = total - start
        if available <= 0 or (duration is not None and duration < 0):
            return None
        if strict_duration and duration and duration > available:
            return None
        count = min(float(duration), available) if duration else available
        components = self.get_components()
        first = round(start * self.fps)
        last = round((start + count) * self.fps)
        soundtrack = components.audio
        if soundtrack is not None:
            rate = soundtrack["sample_rate"]
            soundtrack = {**soundtrack, "waveform": soundtrack["waveform"][..., round(start * rate):round((start + count) * rate)]}
        return InputImpl.VideoFromComponents(VideoComponents(images=components.images[first:last],
            frame_rate=components.frame_rate, audio=soundtrack))


def append_video_clip(images, keep_frames, fps, audio=None, previous=None, soundtrack=None,
                      storage=None, metadata=None, generation_seed=None):
    if not isinstance(images, torch.Tensor) or images.ndim != 4 or images.shape[-1] != 3:
        raise ValueError("Append Video Clip expects an RGB IMAGE batch.")
    if not 1 <= keep_frames <= images.shape[0]:
        raise ValueError("Keep frames must fit the decoded clip.")
    timing = VideoTiming.constant(keep_frames, fps)
    height, width = images.shape[1:3]
    if previous is not None and tuple(previous.get_dimensions()) != (width, height):
        raise ValueError("All clips must have the same dimensions.")
    mode = storage.mode if storage is not None else "temporary"
    previous_mode = ("memory" if isinstance(previous, MemoryClipVideo)
                     else "persistent" if getattr(previous, "_eclipse_run_directory", None) else "temporary")
    if previous is not None and previous_mode != mode:
        raise ValueError("Clip storage mode must remain unchanged within a run.")
    if previous is not None and float(previous.get_frame_rate()) != float(fps):
        raise ValueError("All clips must have the same FPS.")
    if mode == "memory":
        retained = images[:keep_frames].detach().to(device="cpu", copy=True).contiguous()
        chunk_audio = None if audio is None else {**audio, "waveform": audio["waveform"].detach().cpu().clone()}
        chunks = previous.chunks if previous is not None else ()
        return MemoryClipVideo(chunks + ((retained, chunk_audio),), fps, soundtrack)
    if mode not in ("temporary", "persistent"):
        raise ValueError("Unknown clip storage mode.")
    run = (getattr(previous, "_eclipse_run_directory", None) or create_run_directory(storage)
           if mode == "persistent" else None)
    fd, path = tempfile.mkstemp(prefix="EclipseClip_", suffix=".mov", dir=run or folder_paths.get_temp_directory())
    os.close(fd)
    try:
        encode_timed_video(iter(images[:keep_frames]), timing, audio, path,
                           width=width, height=height, lossless=True, preset="ultrafast")
        video = InputImpl.VideoFromFile(path) if run else TemporaryVideo(path, preview_compatible=False)
        result = InputImpl.VideoFromList([previous, video] if previous is not None else [video],
                                        complete_audio=soundtrack)
        if run:
            entries = getattr(previous, "_eclipse_run_entries", ()) + (
                {"file": Path(path).name, "start": 0, "count": keep_frames,
                 **({"seed": str(generation_seed)} if generation_seed is not None else {})},)
            save_run(run, kind="clips", fps=fps, width=width, height=height, entries=entries,
                     audio=soundtrack, metadata=metadata)
            result._eclipse_run_directory = run
            result._eclipse_run_entries = entries
        return result
    except BaseException:
        TemporaryVideo._remove(path)
        raise
