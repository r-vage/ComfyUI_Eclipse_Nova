# Bounded audio replacement for an already encoded native VIDEO.

from fractions import Fraction
from numbers import Integral

import av
import numpy as np
import torch

from .video_timing import check_media_interrupt


def replacement_audio(audio):
    if not isinstance(audio, dict):
        raise TypeError("Audio input is enabled. Connect a valid AUDIO to Save Video's audio input.")
    waveform, rate = audio.get("waveform"), audio.get("sample_rate")
    if isinstance(waveform, torch.Tensor) and waveform.ndim == 3 and waveform.shape[0] == 1:
        waveform = waveform[0]
    if (not isinstance(waveform, torch.Tensor) or waveform.ndim != 2
            or waveform.shape[0] not in (1, 2) or waveform.shape[1] == 0
            or not waveform.is_floating_point()):
        raise ValueError("Replacement AUDIO must contain one nonempty mono or stereo floating-point waveform.")
    if isinstance(rate, bool) or not isinstance(rate, Integral) or rate <= 0:
        raise ValueError("Replacement AUDIO requires a positive integer sample rate.")
    return waveform.detach(), int(rate)


class ReplacementAudioMuxer:
    def __init__(self, container, components):
        self.waveform, self.rate = components
        self.container = container
        self.stream = container.add_stream("aac", rate=self.rate)
        self.stream.layout = "mono" if self.waveform.shape[0] == 1 else "stereo"
        self.position = 0

    def write_until(self, duration):
        target = round(duration * self.rate)
        while self.position < target:
            check_media_interrupt()
            count = min(4096, target - self.position)
            data = np.zeros((self.waveform.shape[0], count), dtype=np.float32)
            available = max(0, min(count, self.waveform.shape[-1] - self.position))
            if available:
                chunk = self.waveform[:, self.position:self.position + available].cpu().float().numpy()
                if not np.isfinite(chunk).all():
                    raise ValueError("Replacement AUDIO contains non-finite samples.")
                data[:, :available] = chunk
            frame = av.AudioFrame.from_ndarray(data, format="fltp", layout=self.stream.layout.name)
            frame.sample_rate = self.rate
            frame.time_base = Fraction(1, self.rate)
            frame.pts = self.position
            self.position += count
            for packet in self.stream.encode(frame):
                self.container.mux(packet)

    def finish(self, duration):
        self.write_until(duration)
        for packet in self.stream.encode():
            self.container.mux(packet)
