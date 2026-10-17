# Lazy source/generated selection shared by the character reference panels.
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.character_references import select_reference
from ..core.node_debug import debug_node

_MISSING = object()
_LOG_PREFIX = "CharacterReferences"


class RvImage_CharacterReferenceSelect(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Character Reference Select [Eclipse Nova]",
            display_name="Character Reference Select",
            category=CATEGORY.MAIN.value + CATEGORY.CHARACTER.value,
            description="Choose the source or generated image using Prepare's mode: reference returns the source; extract/generate request the generated image; disabled returns no image. This lets optional reference branches be skipped without muting nodes. Send the result to the matching Character Reference Pack input.",
            inputs=[
                io.Custom("ECLIPSE_CHARACTER_REFERENCE").Input("reference", tooltip="Connect reference from the matching Character Reference Prepare. Its mode decides whether this node uses the original, requests generated, or returns no image."),
                io.Image.Input("generated", optional=True, lazy=True, tooltip="Connect the decoded image from this reference's preparation sampler. Evaluated only in extract/generate modes. Reference/disabled modes skip this branch through Select; other independent output nodes can still execute it."),
            ],
            outputs=[io.Image.Output("image", tooltip="The chosen single image, or no image when disabled. Connect to the corresponding face/body/clothing/rear input on the Pack; preview it first to check extraction fidelity.")],
        )

    @classmethod
    def check_lazy_status(cls, reference, generated=_MISSING, **kwargs):
        return ["generated"] if reference["mode"] in ("extract", "generate") and generated is None else []

    @classmethod
    @debug_node(_LOG_PREFIX, values=("role", "mode"))
    def execute(cls, reference, generated=None):
        return io.NodeOutput(select_reference(reference, generated))
