import numpy as np
import torch
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.operation_panel import OperationPanel
from ..core.seg_masks import custom_mask_to_segs


class RvMask_ToSEGS(OperationPanel, io.ComfyNode):
    PANEL_KIND = "mask_segs"

    @classmethod
    def operation_schema(cls):
        return io.Schema(
            node_id="Mask to SEGS [Eclipse Nova]",
            display_name="Mask to SEGS",
            category=CATEGORY.MAIN.value + CATEGORY.MASK.value,
            is_input_list=True,
            inputs=[
                io.Mask.Input("mask", tooltip="Input mask tensor."),
                io.Boolean.Input(
                    "combined",
                    default=False,
                    label_on="True",
                    label_off="False",
                    tooltip="Combine all masks into one bounding box.",
                ),
                io.Float.Input(
                    "crop_factor",
                    default=3.0,
                    min=1.0,
                    max=100.0,
                    step=0.1,
                    tooltip="Crop factor around bounding box.",
                ),
                io.Boolean.Input(
                    "bbox_fill",
                    default=False,
                    label_on="enabled",
                    label_off="disabled",
                    tooltip="Fill bounding box with 1.0 in cropped mask.",
                ),
                io.Int.Input(
                    "drop_size",
                    default=10,
                    min=1,
                    max=8192,
                    step=1,
                    tooltip="Minimum contour size to keep.",
                ),
                io.Boolean.Input(
                    "contour_fill",
                    default=False,
                    label_on="enabled",
                    label_off="disabled",
                    tooltip="Fill contours completely.",
                ),
            ],
            outputs=[
                io.Custom("SEGS").Output("segs"),
            ],
        )

    @classmethod
    def execute_operation(
        cls, mask, combined, crop_factor, bbox_fill, drop_size, contour_fill=False
    ):
        if not mask:
            return io.NodeOutput(((0, 0), []))

        # Flatten list/tuple inputs to ensure we process individual tensors
        flat_mask = []
        for m in mask:
            if isinstance(m, (list, tuple)):
                for sub in m:
                    if sub is not None:
                        flat_mask.append(sub)
            elif m is not None:
                flat_mask.append(m)
        mask = flat_mask

        if not mask:
            return io.NodeOutput(((0, 0), []))

        combined = combined[0] if isinstance(combined, list) else combined
        crop_factor = crop_factor[0] if isinstance(crop_factor, list) else crop_factor
        bbox_fill = bbox_fill[0] if isinstance(bbox_fill, list) else bbox_fill
        drop_size = drop_size[0] if isinstance(drop_size, list) else drop_size
        contour_fill = (
            contour_fill[0]
            if isinstance(contour_fill, list) and contour_fill
            else (contour_fill if isinstance(contour_fill, bool) else False)
        )

        h, w = 0, 0
        all_segs = []
        frame_offset = 0

        for item in mask:
            if item is None:
                continue

            if isinstance(item, torch.Tensor):
                if item.ndim == 2:
                    item = item.unsqueeze(0)
            elif isinstance(item, np.ndarray):
                if item.ndim == 2:
                    item = np.expand_dims(item, axis=0)

            # Record dimensions of the first valid mask
            if h == 0 or w == 0:
                h, w = item.shape[1], item.shape[2]

            batch_size = item.shape[0]
            for i in range(batch_size):
                slice_mask = item[i : i + 1]  # Keep 3D shape (1, H, W)

                target_batch_idx = frame_offset + i

                segs = custom_mask_to_segs(
                    slice_mask,
                    combined=combined,
                    crop_factor=crop_factor,
                    bbox_fill=bbox_fill,
                    drop_size=drop_size,
                    is_contour=contour_fill,
                    batch_index=target_batch_idx,
                )
                all_segs.extend(segs)
            frame_offset += batch_size

        return io.NodeOutput(((h, w), all_segs))
