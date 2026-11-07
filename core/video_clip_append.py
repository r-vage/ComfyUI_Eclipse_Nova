# Keep generated video and audio together on disk between loop iterations.
import os
import tempfile

import folder_paths
import torch
from comfy_api.latest import InputImpl

from .video_helpers import TemporaryVideo
from .video_timing import VideoTiming, encode_timed_video


def append_video_clip(images, keep_frames, fps, audio=None, previous=None, soundtrack=None):
    if not isinstance(images, torch.Tensor) or images.ndim != 4 or images.shape[-1] != 3:
        raise ValueError("Append Video Clip expects an RGB IMAGE batch.")
    if not 1 <= keep_frames <= images.shape[0]:
        raise ValueError("Keep frames must fit the decoded clip.")
    timing = VideoTiming.constant(keep_frames, fps)
    height, width = images.shape[1:3]
    if previous is not None and tuple(previous.get_dimensions()) != (width, height):
        raise ValueError("All clips must have the same dimensions.")
    fd, path = tempfile.mkstemp(prefix="EclipseClip_", suffix=".mov", dir=folder_paths.get_temp_directory())
    os.close(fd)
    try:
        encode_timed_video(iter(images[:keep_frames]), timing, audio, path,
                           width=width, height=height, lossless=True, preset="ultrafast")
        video = TemporaryVideo(path, preview_compatible=False)
        return InputImpl.VideoFromList([previous, video] if previous is not None else [video],
                                       complete_audio=soundtrack)
    except BaseException:
        TemporaryVideo._remove(path)
        raise
