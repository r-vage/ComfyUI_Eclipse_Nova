# Image Selector and Image Comparer

**Image Selector** and **Image Comparer** are under **🌒 Eclipse Nova → Image → Save & Preview**. Both use the selected Nova design, collapsible bars, and resizable previews in standard canvas and Nodes 2.0.

## Image Selector

Connect an image batch or list to **images** and run the workflow. The node shows the images and interrupts execution so you can choose what continues downstream.

**Play (▶)** on the right of Mode runs only this node and its required upstream
inputs, filling the selection grid. It remains available when Mode is collapsed.
The existing selection pause handles stopping; no separate Stop toggle is needed.
Choose images and press Confirm to continue the workflow as usual. Play keeps
Auto confirm unchanged; with it enabled, all images are selected automatically
and the partial run ends at this node.

- Click images to select or deselect them. Numbered badges show their output order.
- Shift+click selects a range. **All** or Ctrl/Cmd+A selects everything; Escape clears the selection.
- Double-click an image to open a larger preview. Left/Right or A/D moves through images; Space, S or Enter toggles selection. Escape closes the larger preview.
- Right-click a thumbnail or the larger preview for image actions. Open, Save,
  Copy, Clipspace and Mask Editor use the original full-resolution image. The
  grid itself still loads thumbnails capped at 1024 pixels on the longest side.
- **Layout** chooses an automatic grid or one to six images per row. Large grids scroll inside the node. Resizing the node changes the available preview area.
- **Confirm** sends the selected indices and requeues the workflow. Supported upstream dynamic seed and file-index providers are fixed to the values used for the displayed images.
- **Discard** clears the decision and disables Auto confirm; the next queue pauses for selection again.
- **Auto confirm**, in the Mode bar, passes every incoming image without pausing on subsequent runs. Enabling it on a waiting grid selects all images; press Confirm to resume that interrupted run. This option is session-only and is turned off when a workflow is loaded.

The **images** output is a batch in selection order. Mixed-size images are resized to the first selected image's dimensions. **indices** contains the corresponding zero-based indices.

Selection drafts, order, layout and node size survive workflow reloads while the same backend session and preview files are available. Reloading never confirms or queues work. Changed upstream inputs, deleted previews or a restarted backend require another run to rebuild the grid.

Originals are cached with the thumbnails in ComfyUI's temporary directory,
including alpha and workflow metadata. Confirming a selection reuses those files;
removing the node or replacing the grid removes them. Images already within the preview
size limit share one file for the preview and image actions.

## Image Comparer

Connect originals to **image_a** and results to **image_b**, then run the workflow.

One compact bar combines **Mode: Slide / Click** and **Output: A / B**. Collapse it to show both selections in the summary and leave more room for the preview.

| Control | Behavior |
| --- | --- |
| Slide | Move over the preview to reveal the difference across a movable divider. |
| Click | Hold the left mouse button to see B, then release to see A. Space works while the preview has focus. |
| Output A / B | Choose the complete input side that passes downstream. B is the default; if that side is empty, the other side is used. |
| Pair navigator | Move through batches with the numbered buttons or previous/next arrows. Left/Right works while the preview has focus. |

Pairs use matching indices. If one side is shorter, its first image is reused for the remaining comparisons. A single connected side can be browsed by itself. Pair navigation only changes the preview; it does not select a subset for the output.

Original image tensors, batch grouping, dimensions and alpha channels pass through unchanged. The selected output side is part of the API configuration, so it also works without workflow metadata. Right-click offers **Open Image A/B** and **Save Image A/B** for the displayed pair.

Mode, output choice, pair position, collapsed bar and node size are saved with the workflow. Temporary previews can be restored while their files remain available; run the workflow again if they have expired.

If a restored preview is missing, the comparer clears its saved image references,
pair numbers and image actions, and shows **Preview expired**. Mode, output choice
and node size stay unchanged. A new execution fills the comparison again.
