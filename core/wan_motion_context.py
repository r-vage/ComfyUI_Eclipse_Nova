# A bounded motion tensor with the full audio-clock length expected internally
# by ComfyUI's InfiniteTalk conditioner. Never exposed as an IMAGE output.
from dataclasses import dataclass

import torch


@dataclass(frozen=True)
class WanMotionContext:
    frames: torch.Tensor
    audio_start: int

    @property
    def shape(self):
        return (self.audio_start + self.frames.shape[0], *self.frames.shape[1:])

    def __getitem__(self, key):
        # InfiniteTalk only reads its tail after consulting the logical length.
        count = self.frames.shape[0]
        if not isinstance(key, slice) or key.start != -count or key.stop is not None or key.step is not None:
            raise ValueError("InfiniteTalk requested an unsupported motion-context range.")
        return self.frames


def motion_context(previous_frames, motion_frame_count, audio_start):
    if not isinstance(previous_frames, torch.Tensor) or previous_frames.ndim != 4:
        raise TypeError("previous_frames must be one IMAGE batch.")
    if type(audio_start) is not int or audio_start < 0:
        raise ValueError("audio_start must be a nonnegative frame index.")
    if type(motion_frame_count) is not int or not 1 <= motion_frame_count <= previous_frames.shape[0]:
        raise ValueError("Not enough motion frames.")
    # Clone the small tail so a retained context cannot keep a full batch alive.
    return WanMotionContext(previous_frames[-motion_frame_count:].clone(), audio_start)
