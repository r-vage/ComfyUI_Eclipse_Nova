# Shared SEGS scaling and detailing for the native and structured Detailer nodes.

import numpy as np
import torch

from ..extern.impact import utils as impact_utils
from ..extern.impact.core import SEG
from ..extern.impact.impact_pack import DetailerForEach
from .image_helpers import flatten_images


def fixed_segs_scale_match(segs, target_shape):
    h, w = segs[0]
    th, tw = target_shape[1:3]
    if (h == th and w == tw) or h == 0 or w == 0:
        return segs

    rh, rw = th / h, tw / w
    new_segs = []
    for seg in segs[1]:
        cropped_image = seg.cropped_image
        cropped_mask = seg.cropped_mask
        x1, y1, x2, y2 = seg.crop_region
        bx1, by1, bx2, by2 = seg.bbox

        # Horizontal and vertical coordinates must use their own scale ratios.
        crop_region = int(x1 * rw), int(y1 * rh), int(x2 * rw), int(y2 * rh)
        bbox = int(bx1 * rw), int(by1 * rh), int(bx2 * rw), int(by2 * rh)
        new_w = crop_region[2] - crop_region[0]
        new_h = crop_region[3] - crop_region[1]
        if isinstance(cropped_mask, np.ndarray):
            cropped_mask = torch.from_numpy(cropped_mask)
        if isinstance(cropped_mask, torch.Tensor) and cropped_mask.ndim == 3:
            cropped_mask = torch.nn.functional.interpolate(
                cropped_mask.unsqueeze(0), size=(new_h, new_w), mode="bilinear", align_corners=False,
            ).squeeze(0)
        else:
            cropped_mask = torch.nn.functional.interpolate(
                cropped_mask.unsqueeze(0).unsqueeze(0), size=(new_h, new_w), mode="bilinear", align_corners=False,
            ).squeeze(0).squeeze(0).numpy()

        if cropped_image is not None:
            image_tensor = cropped_image if isinstance(cropped_image, torch.Tensor) else torch.from_numpy(cropped_image)
            cropped_image = impact_utils.tensor_resize(image_tensor, new_w, new_h).numpy()
        new_segs.append(SEG(cropped_image, cropped_mask, seg.confidence, crop_region, bbox, seg.label, seg.control_net_wrapper))

    return (th, tw), new_segs


def detail_images(image, segs, basic_pipe, *, seed, guide_size, guide_size_for,
                  max_size, steps, cfg, sampler_name, scheduler, denoise, feather,
                  noise_mask, force_inpaint, cycle, inpaint_model, noise_mask_feather,
                  tiled_encode, tiled_decode, live_preview=True, scheduler_func_opt=None):
    model, clip, vae, positive, negative = basic_pipe
    enhanced_images, detailed_segs = [], []
    for index, frame in enumerate(flatten_images(image)):
        # Preserve the detailer's per-frame SEG ownership and corrected scaling.
        scaled = fixed_segs_scale_match(segs, frame.shape)
        segments = [seg for seg in scaled[1] if getattr(seg.control_net_wrapper, "batch_index", 0) == index]
        enhanced, _cropped, _enhanced, _alpha, _cnet, new_segs = DetailerForEach.do_detail(
            frame, (scaled[0], segments), model, clip, vae,
            guide_size, guide_size_for, max_size, seed, steps, cfg, sampler_name,
            scheduler, positive, negative, denoise, feather, noise_mask, force_inpaint,
            wildcard_opt=None, detailer_hook=None, refiner_ratio=0.0,
            refiner_model=None, refiner_clip=None, refiner_positive=None, refiner_negative=None,
            cycle=cycle, inpaint_model=inpaint_model, noise_mask_feather=noise_mask_feather,
            scheduler_func_opt=scheduler_func_opt, tiled_encode=tiled_encode,
            tiled_decode=tiled_decode, preview_enabled=live_preview,
        )
        enhanced_images.append(enhanced)
        detailed_segs.extend(new_segs[1])
    return enhanced_images, [(segs[0], detailed_segs)], [basic_pipe]
