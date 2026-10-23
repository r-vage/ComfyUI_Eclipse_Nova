#
# Image Batch Extend With Overlap — blends two image batches at a shared
# overlap region for video generation extension.
#
# When both inputs are connected the overlapping frames are blended and the
# full extended sequence is returned.
# When only one input is connected that batch is returned as-is.
#
# Originally inspired by KJNodes ImageBatchExtendWithOverlap.
#

import comfy.utils  # type: ignore
import torch  # type: ignore
from comfy_api.latest import io  # type: ignore

from ..core import CATEGORY
from ..core.image_blending import (
    BLEND_MODES,
    BLEND_TOOLTIP,
    blend_frames,
    pyramid_blend,
    resolve_blend_mode,
)
from ..core.image_helpers import cat_and_fit_images, flatten_images, unwrap_value
from ..core.logger import log
from ..core.operation_panel import OperationPanel

_LOG_PREFIX = "ImageBatchExtendWithOverlap"

_OVERLAP_SIDE_OPTIONS = ["source", "new_images", "both"]
_OVERLAP_MODE_OPTIONS = [
    *BLEND_MODES,
    "cut",
    "concat",
    "match_ncc",
    "match_ncc+linear",
    "match_ncc+pyramid",
    "match_mse",
    "match_mse+linear",
    "match_mse+pyramid",
    "match_luminance_mse",
    "match_luminance_mse+linear",
    "match_luminance_mse+pyramid",
    "match_gradient_mse",
    "match_gradient_mse+linear",
    "match_gradient_mse+pyramid",
]

# Longest-side pixel size used when downsampling frames before cross-batch comparison.
_MATCH_DOWNSAMPLE_SIZE = 512


def _find_cross_batch_match(
    source: torch.Tensor,
    new_images: torch.Tensor,
    search_frames: int,
    metric: str = "ncc",
    side: str = "both",
) -> tuple:
    # Find the (src_idx, new_idx) pair that minimises visual distance between
    # source[src_idx] and new_images[new_idx].
    #
    # side controls which search windows are used:
    #   both       — scan last N of source × first N of new_images; best pair across both windows
    #   source     — pin new_cut=0 (new_images[0] is the fixed reference); find the source tail
    #                frame that matches the start of new_images best
    #   new_images — pin src_cut to source[-1] (fixed reference); find the new_images head frame
    #                that matches the end of source best
    #
    # Frames are downsampled to _MATCH_DOWNSAMPLE_SIZE px before comparison so
    # the operation is fast even for large HD batches.
    #
    # Uses the same pairwise matrix approach as SaveVideo's _find_loop_pair:
    #   ||a-b||² = ||a||² + ||b||² − 2(a·b)   (avoids [S,N,px] memory)
    #
    # Metrics:
    #   ncc           — normalized cross-correlation (higher = better); invariant
    #                   to per-frame brightness scale and offset
    #   mse           — mean squared pixel error (lower = better)
    #   luminance_mse — BT.601 grayscale MSE; ignores hue/saturation differences
    #   gradient_mse  — edge-magnitude MSE; ignores color, matches structure only
    #
    # Returns:
    #     (src_absolute_idx: int, new_absolute_idx: int, score: float)
    n_src = source.shape[0]
    n_new = new_images.shape[0]
    search_n_src = max(1, min(search_frames, n_src))
    search_n_new = max(1, min(search_frames, n_new))

    if side == "source":
        # Pin new_images[0] as the fixed reference; scan only the source tail.
        src_start = max(0, n_src - search_n_src)
        new_end = 1
    elif side == "new_images":
        # Pin source[-1] as the fixed reference; scan only the new_images head.
        src_start = n_src - 1
        new_end = min(n_new, search_n_new)
    else:  # both
        src_start = max(0, n_src - search_n_src)
        new_end = min(n_new, search_n_new)

    h = min(source.shape[1], new_images.shape[1])
    w = min(source.shape[2], new_images.shape[2])
    scale = _MATCH_DOWNSAMPLE_SIZE / max(h, w)
    ds_h = max(1, round(h * scale))
    ds_w = max(1, round(w * scale))

    interp = torch.nn.functional.interpolate
    src_ds = interp(
        source[src_start:, ..., :3].permute(0, 3, 1, 2).float(),
        size=(ds_h, ds_w),
        mode="bilinear",
        align_corners=False,
    )  # [S, 3, ds_h, ds_w]
    new_ds = interp(
        new_images[:new_end, ..., :3].permute(0, 3, 1, 2).float(),
        size=(ds_h, ds_w),
        mode="bilinear",
        align_corners=False,
    )  # [N, 3, ds_h, ds_w]
    S, N = src_ds.shape[0], new_ds.shape[0]

    if metric == "ncc":
        s_flat = src_ds.reshape(S, -1)
        n_flat = new_ds.reshape(N, -1)
        s_norm = s_flat - s_flat.mean(dim=1, keepdim=True)
        n_norm = n_flat - n_flat.mean(dim=1, keepdim=True)
        # [S, N] pairwise NCC — higher = better
        sim = (s_norm @ n_norm.T) / (
            s_norm.norm(dim=1, keepdim=True) * n_norm.norm(dim=1).unsqueeze(0) + 1e-8
        )
        flat_best = int(sim.argmax().item())
        best_s, best_n = flat_best // N, flat_best % N
        score = float(sim[best_s, best_n].item())

    else:
        # MSE family: ||a-b||² = ||a||² + ||b||² − 2(a·b), lower = better
        if metric == "luminance_mse":
            luma_w = torch.tensor([0.299, 0.587, 0.114], device=src_ds.device).view(
                1, 3, 1, 1
            )
            s_feat = (src_ds * luma_w).sum(dim=1).reshape(S, -1)
            n_feat = (new_ds * luma_w).sum(dim=1).reshape(N, -1)
        elif metric == "gradient_mse":

            def _grad_mag(img: torch.Tensor) -> torch.Tensor:
                dx = img[:, :, :, 1:] - img[:, :, :, :-1]
                dy = img[:, :, 1:, :] - img[:, :, :-1, :]
                return (
                    (dx[:, :, :-1, :].pow(2) + dy[:, :, :, :-1].pow(2))
                    .sqrt()
                    .mean(dim=1)
                )

            s_feat = _grad_mag(src_ds).reshape(S, -1)
            n_feat = _grad_mag(new_ds).reshape(N, -1)
        else:  # mse
            s_feat = src_ds.reshape(S, -1)
            n_feat = new_ds.reshape(N, -1)
        Nf = s_feat.shape[1]
        s_sq = s_feat.pow(2).sum(dim=1) / Nf  # [S]
        n_sq = n_feat.pow(2).sum(dim=1) / Nf  # [N]
        cross = (s_feat @ n_feat.T) / Nf  # [S, N]
        scores = s_sq.unsqueeze(1) + n_sq.unsqueeze(0) - 2 * cross  # [S, N]
        flat_best = int(scores.argmin().item())
        best_s, best_n = flat_best // N, flat_best % N
        score = float(scores[best_s, best_n].item())

    return src_start + best_s, best_n, score


def _resize_to_match(
    images: torch.Tensor, target_h: int, target_w: int
) -> torch.Tensor:
    # Scale to fill target size (preserving aspect ratio) then center-crop to exact dimensions.
    # Mirrors the "crop" fit mode in core/image_resize.py: scale = max(tw/W, th/H).
    h, w = images.shape[1], images.shape[2]
    if h == target_h and w == target_w:
        return images

    # Scale so both dimensions meet or exceed the target.
    scale = max(target_w / w, target_h / h)
    inter_w = max(round(w * scale), target_w)
    inter_h = max(round(h * scale), target_h)

    # Resize via comfy's upscaler (BHWC → BCHW → upscale → BHWC).
    samples = images.movedim(-1, 1)
    samples = comfy.utils.common_upscale(
        samples, inter_w, inter_h, "bilinear", "disabled"
    )
    images = samples.movedim(1, -1)

    # Center-crop to exact target dimensions.
    cx = (inter_w - target_w) // 2
    cy = (inter_h - target_h) // 2
    return images[:, cy : cy + target_h, cx : cx + target_w, :]


class RvImage_BatchExtendWithOverlap(OperationPanel, io.ComfyNode):
    PANEL_KIND = "batch_overlap"

    @classmethod
    def operation_schema(cls):
        return io.Schema(
            node_id="Image Batch Extend With Overlap [Eclipse Nova]",
            display_name="Image Batch Extend With Overlap",
            description=(
                "Extends a video batch by blending two image sequences at an overlapping region.\n"
                "Both inputs connected: blends the overlap and returns the full extended sequence.\n"
                "Only source_images: returned as-is.\n"
                "Only new_images: returned as-is.\n"
                "If the two inputs differ in size, new_images is center-cropped and resized to match source_images."
            ),
            category=CATEGORY.MAIN.value + CATEGORY.IMAGE_BATCH.value,
            inputs=[
                io.Image.Input(
                    "source_images",
                    optional=True,
                    tooltip="The source (first) image batch. Optional — when not connected, new_images is returned as-is.",
                ),
                io.Int.Input(
                    "overlap",
                    default=5,
                    min=0,
                    max=4096,
                    step=1,
                    tooltip=(
                        "Number of overlapping frames between source and new images for blending modes.\n"
                        "0 = hard cut: the two batches are concatenated directly, overlap_mode is ignored.\n"
                        "For match_* modes (pure): defines how many frames from each end are scanned — "
                        "overlap_side=both scans last N of source AND first N of new_images; "
                        "source/new_images pins one side and scans only the other.\n"
                        "For match_*+blend hybrid modes: used as both the search window size AND "
                        "the blend window applied starting at the matched cut point."
                    ),
                ),
                io.Combo.Input(
                    "overlap_side",
                    options=_OVERLAP_SIDE_OPTIONS,
                    default="source",
                    tooltip=(
                        "Controls which side(s) are searched or trimmed. Meaning depends on overlap_mode.\n"
                        "\nFor cut mode:\n"
                        "  source: drops the last N frames of source_images.\n"
                        "  new_images: drops the first N frames of new_images.\n"
                        "  both: drops last N from source AND first N from new_images simultaneously\n"
                        "  (removes generated ramp/fade frames from both edges at once).\n"
                        "\nFor match_* modes:\n"
                        "  both: scan last N of source × first N of new_images — find the best-matching pair from both windows (default).\n"
                        "  source: pin new_images[0] as reference, search only source's tail — finds where source best matches the start of new_images.\n"
                        "  new_images: pin source[-1] as reference, search only new_images' head — finds where new_images best matches the end of source.\n"
                        "\nIgnored for all other blend modes."
                    ),
                ),
                io.Combo.Input(
                    "overlap_mode",
                    options=_OVERLAP_MODE_OPTIONS,
                    default="pyramid_blend",
                    tooltip=(
                        "How to blend the overlapping region.\n"
                        "linear_blend: linear cross-fade.\n"
                        "ease_in_out: S-curve cross-fade (slow start/end).\n"
                        "filmic_crossfade: gamma-correct (2.2) cross-fade — better in bright regions.\n"
                        "perceptual_crossfade: LAB-space blend — avoids hue shifts across strong color differences (requires kornia).\n"
                        "average: fixed 50/50 mix of all overlap frames — no directional fade, both generations contribute equally.\n"
                        "dissolve: random pixel-level selection per frame (dithered transition, film-grain look).\n"
                        "pyramid_blend: multi-scale Laplacian pyramid — each frequency band blended independently; sharpest quality.\n"
                        "clock_wipe: clockwise sweep from 12 o'clock — a hard edge rotates across the frame like a clock hand.\n"
                        "clock_wipe_ccw: same sweep counter-clockwise.\n"
                        "wipe_left: hard edge sweeps left→right across the frame.\n"
                        "wipe_right: hard edge sweeps right→left.\n"
                        "wipe_top: hard edge sweeps top→bottom.\n"
                        "wipe_bottom: hard edge sweeps bottom→top.\n"
                        f"{BLEND_TOOLTIP} Overlap batches estimate motion for each corresponding frame pair.\n"
                        "cut: drops overlap frames — overlap_side=source removes last N from source; overlap_side=new_images removes first N from new_images; overlap_side=both removes last N from source AND first N from new_images simultaneously.\n"
                        "concat: direct concatenation, no frames lost, overlap parameter ignored.\n"
                        "match_ncc / match_mse / match_luminance_mse / match_gradient_mse: scan frames "
                        "of source against frames of new_images (window size = overlap) and hard-cut at the most "
                        "visually similar pair — no blending needed since the frames already match. "
                        "overlap_side=both searches both ends (default); source pins new_images[0] as reference; "
                        "new_images pins source[-1] as reference. "
                        "ncc is invariant to brightness/color drift; mse is fastest; luminance_mse ignores hue; "
                        "gradient_mse matches structure only.\n"
                        "match_*+linear / match_*+pyramid: hybrid — finds the best matching pair exactly as above, "
                        "then instead of a hard cut, applies a linear or pyramid blend window of `overlap` frames "
                        "starting at that matched position. Solves the model ramp-in freeze: the blend smooths "
                        "the near-static tail/head frames rather than cutting through them abruptly."
                    ),
                ),
                io.Image.Input(
                    "new_images",
                    optional=True,
                    tooltip="The new (second) image batch to extend with. Optional — when not connected, source_images is returned as-is.",
                ),
            ],
            outputs=[
                io.Image.Output(
                    "images",
                    tooltip="The extended image batch with the overlap region blended, or whichever single input was connected.",
                ),
            ],
            is_input_list=True,
        )

    @classmethod
    def execute_operation(
        cls, overlap, overlap_side, overlap_mode, source_images=None, new_images=None
    ):
        overlap = unwrap_value(overlap, 1)
        overlap_side = unwrap_value(overlap_side, "both")
        overlap_mode = unwrap_value(overlap_mode, "pyramid_blend")

        flat_src = flatten_images(source_images)
        flat_new = flatten_images(new_images)

        if not flat_src and not flat_new:
            raise ValueError(
                "At least one of source_images or new_images must be connected."
            )

        if not flat_src:
            new_images_tensor = cat_and_fit_images(flat_new, log_prefix=_LOG_PREFIX)
            return io.NodeOutput(new_images_tensor)

        if not flat_new:
            source_images_tensor = cat_and_fit_images(flat_src, log_prefix=_LOG_PREFIX)
            return io.NodeOutput(source_images_tensor)

        source_images = cat_and_fit_images(flat_src, log_prefix=_LOG_PREFIX)
        new_images = cat_and_fit_images(flat_new, log_prefix=_LOG_PREFIX)

        if source_images is None or new_images is None:
            return io.NodeOutput(None)

        # Resize new_images to match source if dimensions differ.
        target_h, target_w = source_images.shape[1], source_images.shape[2]
        if new_images.shape[1] != target_h or new_images.shape[2] != target_w:
            log.warning(
                _LOG_PREFIX,
                f"new_images size {new_images.shape[2]}x{new_images.shape[1]} differs from "
                f"source_images {target_w}x{target_h} — center-cropping and resizing new_images to match.",
            )
            new_images = _resize_to_match(new_images, target_h, target_w)

        # Hard cut: overlap=0 → concatenate directly, no blending, no frame loss.
        # Must be intercepted here because source[:-0] == source[:0] (empty) in Python.
        if overlap == 0:
            log.msg(
                _LOG_PREFIX,
                f"overlap=0: hard cut — concatenating {len(source_images)} + {len(new_images)} frames.",
            )
            return io.NodeOutput(torch.cat((source_images, new_images), dim=0))

        # match_* modes — find the best-matching cut pair, then either hard-cut or blend a window.
        if overlap_mode.startswith("match_"):
            rest = overlap_mode[len("match_") :]
            if "+" in rest:
                metric, blend_type = rest.split("+", 1)
            else:
                metric, blend_type = rest, None
            try:
                src_cut, new_cut, match_score = _find_cross_batch_match(
                    source_images, new_images, overlap, metric, side=overlap_side
                )
                if blend_type is None:
                    # Pure hard cut at the match point.
                    log.msg(
                        _LOG_PREFIX,
                        f"Match cut ({metric}, side={overlap_side}): src={src_cut}/{len(source_images) - 1}, "
                        f"new={new_cut}/{len(new_images) - 1}, score={match_score:.5f}",
                    )
                    return io.NodeOutput(
                        torch.cat(
                            (source_images[: src_cut + 1], new_images[new_cut:]), dim=0
                        )
                    )
                else:
                    # Hybrid: blend a window of `overlap` frames starting at the match point.
                    actual_w = min(
                        overlap, len(source_images) - src_cut, len(new_images) - new_cut
                    )
                    log.msg(
                        _LOG_PREFIX,
                        f"Match+blend ({metric}+{blend_type}, side={overlap_side}): "
                        f"src={src_cut}/{len(source_images) - 1}, "
                        f"new={new_cut}/{len(new_images) - 1}, score={match_score:.5f}, blend_window={actual_w}",
                    )
                    prefix_h = source_images[:src_cut]
                    blend_src_h = source_images[src_cut : src_cut + actual_w]
                    blend_dst_h = new_images[new_cut : new_cut + actual_w]
                    suffix_h = new_images[new_cut + actual_w :]
                    alpha_h = torch.linspace(
                        0,
                        1,
                        actual_w + 2,
                        device=blend_src_h.device,
                        dtype=blend_src_h.dtype,
                    )[1:-1]
                    alpha_h = alpha_h.view(-1, 1, 1, 1)
                    if blend_type == "pyramid":
                        blended_h = pyramid_blend(blend_src_h, blend_dst_h, alpha_h)
                    else:  # linear
                        blended_h = (1 - alpha_h) * blend_src_h + alpha_h * blend_dst_h
                    return io.NodeOutput(
                        torch.cat((prefix_h, blended_h, suffix_h), dim=0)
                    )
            except Exception as e:
                label = (
                    f"match_{metric}"
                    if blend_type is None
                    else f"match_{metric}+{blend_type}"
                )
                log.warning(_LOG_PREFIX, f"{label} failed, falling back to concat: {e}")
                return io.NodeOutput(torch.cat((source_images, new_images), dim=0))

        # Blend modes — compute actual_overlap and run the blend.
        # Clamp to the shorter of the two batches so slicing never produces empty tensors.
        actual_overlap = min(overlap, len(source_images), len(new_images))
        if actual_overlap != overlap:
            log.warning(
                _LOG_PREFIX,
                f"overlap ({overlap}) exceeds batch length (source={len(source_images)}, new={len(new_images)}), clamped to {actual_overlap}.",
            )

        prefix = source_images[:-actual_overlap]

        blend_src = source_images[-actual_overlap:]
        blend_dst = new_images[:actual_overlap]

        suffix = new_images[actual_overlap:]

        if overlap_mode == "cut":
            if overlap_side == "source":
                extended_images = torch.cat(
                    (source_images[:-actual_overlap], new_images), dim=0
                )
            elif overlap_side == "both":
                extended_images = torch.cat(
                    (source_images[:-actual_overlap], new_images[actual_overlap:]),
                    dim=0,
                )
            else:  # new_images
                extended_images = torch.cat(
                    (source_images, new_images[actual_overlap:]), dim=0
                )

        elif overlap_mode == "concat":
            extended_images = torch.cat((source_images, new_images), dim=0)

        else:
            if overlap_mode not in BLEND_MODES:
                log.warning(_LOG_PREFIX, f"Unknown overlap_mode '{overlap_mode}', falling back to linear_blend.")
                overlap_mode = "linear_blend"
            alpha = torch.linspace(0, 1, actual_overlap + 2, device=blend_src.device, dtype=blend_src.dtype)[1:-1]
            blended = blend_frames(blend_src, blend_dst, alpha.view(-1, 1, 1, 1), resolve_blend_mode(overlap_mode))
            extended_images = torch.cat((prefix, blended, suffix), dim=0)

        return io.NodeOutput(extended_images)
