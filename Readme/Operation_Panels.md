# Operation panels

The fixed-input tools use the Nova panel design under their final names.
Find them in their usual Eclipse Nova menu categories. These panels replace
the previous interfaces; the temporary `_v2` names have been removed.

These panels follow the selected Nova design in classic canvas and Nodes 2.0.
Small tools use a flat row or grid. Larger tools group settings into collapsible,
pinnable sections; mode bars select modes or enable features. Dropdowns have search.
The values, open sections and text-area sizes are saved with the workflow.

## Available nodes

| Area | Nodes |
| --- | --- |
| Image batches | Batch Slice; Image Batch Strip; Image Batch Extend With Overlap; Image Batch Extend With RIFE |
| Image dimensions and tiles | Image Align Size; Inset & Crop; Tile Split; Tile Assembly; Tile Decode & Assembly; Resolution Scale |
| Masks and conditioning | Mask to SEGS; SEGS Preview Simple; ControlNet Set Union Types (Flux) |
| Audio | Loop Align Silence; Loop Calculator (Audio); Transcribe Audio |
| Video and timing | Video Frame Consistency; Upscale Video; Trim to Shortest; Loop Calculator; Keep Calculator; RIFE Multiplier |
| Frame timelines | Decode and Append Timeline; Trim Frame Timeline |
| WAN planning | WAN LipSync Timeline Planner; WAN LipSync Plan Step |
| Text and annotations | Replace String; String from List; Indices to List; Shot Plan Slice; Markdown Note |
| Paths and filenames | Add Folder; Add Filename Prefix |

Routing, pipe, primitive-value and dynamic-input nodes retain their current
interfaces. Nodes with only data sockets need no settings panel. Existing panel
versions are not duplicated.

## Connected overrides

Relevant settings have explicit optional inputs because controls inside a panel
cannot be converted into sockets. A connected non-`None` value takes priority;
disconnecting it restores use of the saved local value. Zero, `False` and empty
text count as supplied values, subject to the setting's normal bounds.

The inputs cover frame rates and loop counts, frame ranges, image and tile
dimensions, mask settings, selected text and filename values. They include the
settings driven by connections in the saved character and video workflows.
Other data sockets and output contracts stay the same, including list outputs.

Connected controls show an **input** indication. If a connected mode decides
which controls are relevant, the panel keeps those controls accessible until the
mode is resolved during execution.

## Controls and results

- **Image Align Size:** Crop, Pad and Resize share one mode bar. Padding and
  interpolation controls appear for the corresponding mode.
- **RIFE extension:** Interpolation settings appear after choosing a RIFE model.
  Selecting `none` retains the existing transition without RIFE inference.
- **Video Frame Consistency:** Include buttons control colour normalization,
  histogram matching, luminance, temporal smoothing and sharpening. Each feature
  exposes its relevant settings.
- **Upscale Video:** Model selection refreshes when opened. Output size and
  Processing have separate sections; custom dimensions retain connected overrides.
- **Transcribe Audio, Loop Align Silence and Upscale Video:** A collapsed result
  section displays the last transcript or report after execution. Opening another
  section does not erase it.
- **SEGS Preview Simple:** Segment images use a resizable DOM preview that keeps
  their aspect ratio. The first output, SEGS, passes the input through unchanged;
  connect it to downstream processing to include the preview in that execution
  branch. IMAGE is the second output and contains the masked segment images.
- **Markdown Note:** Edit Markdown, then select Preview. Double-click rendered
  text to edit it again. The note remains a workflow annotation and does not execute.

Panels update on edits, connections and normal lifecycle events. They do not poll
for settings or inspect the entire canvas during rendering. Model execution and
optional dependencies remain those of the original tools.

Add these nodes using their final names. Their settings are stored as structured
configuration. Previous native-widget layouts and temporary `_v2` node IDs are
not registered, and there is no automatic workflow conversion.
