# Bidirectional optical-flow morphs with bounded, reusable motion estimation.
import math

import cv2
import numpy as np
import torch

from .video_timing import check_media_interrupt

_FLOW_MAX_SIDE = 512


class MorphPair:
    # Own only the current image pair and its small flow fields; never a video.
    def __init__(self, source, target):
        if not isinstance(source, torch.Tensor) or not isinstance(target, torch.Tensor):
            raise TypeError("Morph expects floating image tensors.")
        if (source.ndim != 3 or source.shape != target.shape or min(source.shape) < 1
                or source.shape[-1] not in (1, 3, 4) or not source.is_floating_point() or not target.is_floating_point()):
            raise ValueError("Morph expects equally sized HWC images with 1, 3 or 4 channels.")
        check_media_interrupt()
        self.device, self.dtype = source.device, source.dtype
        self.first, self.second = source, target
        self.source = source.detach().to(device="cpu", dtype=torch.float32).contiguous().numpy()
        self.target = target.detach().to(device="cpu", dtype=torch.float32).contiguous().numpy()
        if not np.isfinite(self.source).all() or not np.isfinite(self.target).all():
            raise ValueError("Morph image pixels must be finite.")
        self.height, self.width = self.source.shape[:2]
        scale = min(1.0, _FLOW_MAX_SIDE / max(self.width, self.height))
        size = (max(1, round(self.width * scale)), max(1, round(self.height * scale)))

        def grayscale(image):
            # Reduce before quantizing so high-resolution images do not need an
            # additional full-size RGB8 copy merely to estimate motion.
            small = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
            if small.ndim == 3:
                small = cv2.cvtColor(small[..., :3], cv2.COLOR_RGB2GRAY)
            return np.clip(small * 255, 0, 255).round().astype(np.uint8)

        first, second = grayscale(self.source), grayscale(self.target)
        self.grid_x, self.grid_y = np.meshgrid(np.arange(size[0], dtype=np.float32), np.arange(size[1], dtype=np.float32))
        self.scale = np.array((self.width / size[0], self.height / size[1]), dtype=np.float32)
        if min(size) < 8 or np.array_equal(first, second):
            # Tiny or unchanged luminance has no useful motion to estimate.
            self.forward = self.backward = np.zeros((*first.shape, 2), dtype=np.float32)
        else:
            self.forward = self._flow(first, second)
            self.backward = self._flow(second, first)

    @staticmethod
    def _flow(first, second):
        check_media_interrupt()
        # Keep the motion neighborhood proportional to the analysis size, so
        # resizing an image does not strand large, low-texture features.
        window = max(17, (max(first.shape) // 10) | 1)
        flow = cv2.calcOpticalFlowFarneback(first, second, None, .5, 5, window, 5, 7, 1.5, 0)
        check_media_interrupt()
        if not np.isfinite(flow).all():
            raise ValueError("Morph could not estimate finite image motion.")
        return flow

    def _warp(self, image, flow, fraction):
        # Flow is defined on the source grid. Solve the inverse lookup on the
        # small grid instead of treating forward displacement as a remap.
        displacement = -fraction * flow
        for _ in range(4):
            sampled = cv2.remap(flow, self.grid_x + displacement[..., 0], self.grid_y + displacement[..., 1],
                                cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            displacement = .5 * (displacement - fraction * sampled)
        displacement = cv2.resize(displacement, (self.width, self.height), interpolation=cv2.INTER_LINEAR) * self.scale
        warped = cv2.remap(image, np.arange(self.width, dtype=np.float32)[None, :] + displacement[..., 0],
                          np.arange(self.height, dtype=np.float32)[:, None] + displacement[..., 1],
                          cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        return warped[..., None] if warped.ndim == 2 else warped

    def frame(self, fraction):
        fraction = float(fraction)
        if not math.isfinite(fraction) or not 0 <= fraction <= 1:
            raise ValueError("Morph progress must be between zero and one.")
        check_media_interrupt()
        if fraction == 0:
            return self.first
        elif fraction == 1:
            return self.second.to(device=self.device, dtype=self.dtype)
        else:
            first = self._warp(self.source, self.forward, fraction)
            check_media_interrupt()
            second = self._warp(self.target, self.backward, 1 - fraction)
            pixels = (1 - fraction) * first + fraction * second
        return torch.from_numpy(pixels).to(device=self.device, dtype=self.dtype)
