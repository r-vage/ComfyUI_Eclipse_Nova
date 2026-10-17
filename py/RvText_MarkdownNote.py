from comfy_api.latest import io  # type: ignore

from ..core import CATEGORY
from ..core.operation_panel import OperationPanel


class RvText_MarkdownNote(OperationPanel, io.ComfyNode):
    PANEL_KIND = "note"

    @classmethod
    def operation_schema(cls):
        return io.Schema(
            node_id="Markdown Note [Eclipse Nova]",
            display_name="Markdown Note",
            category=CATEGORY.MAIN.value + CATEGORY.TEXT.value,
            description=(
                "Frontend-only Markdown annotation with a resizable, scrollable "
                "preview. Double-click to edit and leave the editor to preview."
            ),
            inputs=[
                io.String.Input(
                    "text",
                    default="",
                    multiline=True,
                    socketless=True,
                    tooltip="Markdown annotation text stored with the workflow.",
                ),
            ],
            outputs=[],
        )

    @classmethod
    def execute_operation(cls, text=""):
        # The frontend marks this as virtual, so prompt execution never reaches here.
        return io.NodeOutput()
