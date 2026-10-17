# Image Preview and Show Any Stop

![Image Preview showing the actual sample image inside a resizable review panel](assets/nova-image-preview.png)

**Show Any Stop** and **Image Preview** use the shared Eclipse
Nova design in standard canvas and Nodes 2.0. Each has a collapsible **Mode** bar
and a resizable preview. **Stop** defaults off.

**Play (▶)** and the existing **Stop (■)** toggle sit together on the right of
Mode. When collapsed, only Play remains visible; the summary shows Stop's state.
Expand Mode to change Stop. Play requests one native
ComfyUI run of this node and its upstream dependencies. It works inside subgraphs
and does not request downstream nodes, so Stop does not need to be enabled.
Play leaves the Stop setting unchanged; any enabled Stop upstream still applies.
Seeds on unrelated Nova nodes do not advance during a partial run.

## Stop and cached results

Enable **Stop** to interrupt the current workflow after the node prepares and
displays its result. Downstream nodes wait for a subsequent run.

Queue again with unchanged inputs and settings: ComfyUI reuses the cached result
and continues without another interruption. Changed inputs cause the node to run
and stop again. Changing the Stop setting also counts as a configuration change.
The nodes use ComfyUI's normal cache; clearing that cache or restarting ComfyUI
means the next result must execute again.

Disable **Stop** for ordinary display and passthrough. Stop does not delete queued
jobs, and collapsing the Mode bar does not change its setting.

## Show Any

Connect any value to **anything**. The read-only text area displays strings,
numbers, lists, dictionaries and tensor information. Multiple input values are
separated by blank lines. Select and copy text as usual; long results scroll.

The output preserves the original values and their list order. It does not
convert the forwarded data into display strings. Image tensors are displayed as
text here; use the image preview to see their pixels.

## Image Preview

Connect an IMAGE or MASK to **image | mask**. Masks display as grayscale: 0 is
black, 1 is white, and intermediate values remain gray. The output socket follows
the connected type, forwarding images as IMAGE and masks as MASK.

A single frame fills the available preview area
while keeping its aspect ratio. Multiple frames appear in the existing adaptive
grid. Click a thumbnail to inspect a frame, use left/right arrows to navigate,
and use the close control to return to the grid. Double-click also switches
between the grid and single-frame view.

Resize the node to resize its preview. Receiving another image keeps the chosen
node dimensions. Preview PNGs use ComfyUI's temporary directory and metadata
settings. The output preserves original batches, list order, mixed frame sizes,
image alpha and mask values; previewing does not resize, flatten or convert the
forwarded data. Both image and mask batches support the same grid and Stop controls.

## Workflow state and subgraphs

Stop and the collapsed Mode bar are saved with the workflow. Cloned nodes keep
independent settings. Switching between standard canvas and Nodes 2.0 keeps the
same controls and current preview.

Inside a subgraph, use the subgraph's **DOM previews** menu to expose the text or
image preview on its parent node, as with the existing DOM display nodes.
