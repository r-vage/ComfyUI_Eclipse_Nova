import torch  # type: ignore
import comfy.utils  # type: ignore

from comfy_api.latest import io  # type: ignore

from ..core import CATEGORY
from ..core.image_helpers import flatten_images, cat_and_fit_images, flatten_masks, is_conditioning
from ..core.batch_helpers import batch_conditionings, batch_latents


def _convert_image_list_to_batch(images):
    flat_images = flatten_images(images)
    if not flat_images:
        return None
    return cat_and_fit_images(flat_images, log_prefix="ToBatch")


def _convert_mask_list_to_batch(mask):
    masks_3d = [m.unsqueeze(0) for m in flatten_masks(mask)]
    if not masks_3d:
        return None
    target_shape = masks_3d[0].shape[1:]  # [H, W]

    upscaled_masks = []
    for m in masks_3d:
        if m.shape[1:] != target_shape:
            m = m.unsqueeze(1).repeat(1, 3, 1, 1)
            m = comfy.utils.common_upscale(
                m, target_shape[1], target_shape[0], "lanczos", "center"
            )
            m = m[:, 0, :, :]
        upscaled_masks.append(m)

    return torch.cat(upscaled_masks, dim=0)


class RvConversion_ToBatch(io.ComfyNode):

    @classmethod
    def define_schema(cls):
        type_template = io.MatchType.Template("dynamic_type")
        return io.Schema(
            node_id="To Batch [Eclipse Nova]",
            display_name="Convert to Batch",
            category=CATEGORY.MAIN.value + CATEGORY.CONVERSION.value,
            description="Dynamic To Batch converter — automatically detects the type of the connected "
            "input list (Image, Mask, Latent, Conditioning, or Primitives) and outputs them as a combined "
            "batch format. Primitives (strings, numbers) are merged into a single comma-separated string.",
            is_input_list=True,
            inputs=[
                io.MatchType.Input(
                    "input",
                    template=type_template,
                    tooltip="Any list of values or tensors to combine into a batch",
                ),
            ],
            outputs=[
                io.MatchType.Output(
                    template=type_template,
                    is_output_list=False,
                    tooltip="The combined batch format",
                ),
            ],
        )

    @classmethod
    def execute(cls, input):
        if input is None or len(input) == 0:
            return io.NodeOutput(None)

        first_item = input[0]

        if is_conditioning(first_item):
            return io.NodeOutput(batch_conditionings(input))

        if isinstance(first_item, dict) and "samples" in first_item:
            res = batch_latents(input)
            return io.NodeOutput(res)

        if isinstance(first_item, torch.Tensor):
            if first_item.ndim in (2, 3):
                res = _convert_mask_list_to_batch(input)
            else:
                res = _convert_image_list_to_batch(input)
            return io.NodeOutput(res)

        if isinstance(first_item, (str, int, float, bool)):
            res_str = ", ".join(map(str, input))
            return io.NodeOutput(res_str)

        return io.NodeOutput(input)
