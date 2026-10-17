import torch  # type: ignore
import numpy as np  # type: ignore

from comfy_api.latest import io  # type: ignore

from ..core import CATEGORY
from ..core.image_helpers import is_conditioning, flatten_masks, flatten_images
from ..core.batch_helpers import split_conditioning, split_latent


class RvConversion_ToList(io.ComfyNode):

    @classmethod
    def define_schema(cls):
        type_template = io.MatchType.Template("dynamic_type")
        return io.Schema(
            node_id="To List [Eclipse Nova]",
            display_name="Convert to List",
            category=CATEGORY.MAIN.value + CATEGORY.CONVERSION.value,
            description="Dynamic To List converter — automatically detects the type of the connected "
            "input (Image, Mask, Latent, Conditioning, etc.) and outputs a list of individual items. "
            "Requires no dropdown selection.",
            is_input_list=True,
            inputs=[
                io.MatchType.Input(
                    "input",
                    template=type_template,
                    tooltip="Any value or batch to convert to list format",
                ),
            ],
            outputs=[
                io.MatchType.Output(
                    template=type_template,
                    is_output_list=True,
                    tooltip="The converted list format",
                ),
            ],
        )

    @classmethod
    def execute(cls, input):
        if input is None:
            return io.NodeOutput([])

        flat_list = []

        def _process(item):
            if is_conditioning(item):
                flat_list.extend(split_conditioning(item))
            elif isinstance(item, (list, tuple)):
                for sub in item:
                    _process(sub)
            elif isinstance(item, dict) and "samples" in item:
                flat_list.extend(split_latent(item))
            elif isinstance(item, torch.Tensor):
                # Canonical IMAGE is BHWC; canonical MASK is BHW (even at width 1/3/4).
                if item.dim() in (2, 3):
                    flat_list.extend(mask.unsqueeze(0) for mask in flatten_masks(item))
                elif item.dim() == 4:
                    flat_list.extend(flatten_images(item))
                else:
                    flat_list.append(item)
            elif isinstance(item, np.ndarray):
                if item.ndim == 4:
                    for i in range(item.shape[0]):
                        flat_list.append(item[i : i + 1, ...])
                elif item.ndim == 3:
                    flat_list.append(np.expand_dims(item, axis=0))
                else:
                    flat_list.append(item)
            elif isinstance(item, str):
                if "\n" in item:
                    flat_list.extend([line.strip() for line in item.split("\n") if line.strip()])
                elif "," in item:
                    flat_list.extend([part.strip() for part in item.split(",")])
                else:
                    flat_list.append(item)
            elif item is not None:
                flat_list.append(item)

        _process(input)
        return io.NodeOutput(flat_list)
