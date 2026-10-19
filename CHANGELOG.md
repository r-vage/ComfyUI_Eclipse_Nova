# Changelog

## 2026-10-19

### Version: 1.0.4

- **Fix**
  - Give each intentional MiniMax H3 camera cut one early timestamp inside the discarded warmup, allowing the new shot to settle before visible output while preserving frame ranges and audio timing.
  - Align MiniMax H3 technical cuts to activity gaps in multi-image timelines while respecting warmup, endpoint and render limits.
  - Detect softer activity onsets before sustained high activity, and retain surrounding gap evidence when constraining cut positions.
- **Docs**
  - Explain hidden camera-cut timing, activity-gap placement and rendered transition checks.
- **Changed files**
  - core/audio_timeline.py
  - core/minimax_h3_segment_plan.py
  - core/minimax_h3_segmented_timeline.py
  - core/minimax_h3_segmented_conditioning.py
  - Readme/MiniMax_H3_Audio_Planner.md
  - pyproject.toml

### Version: 1.0.3

- **Feat**
  - Add Neutral Jade, Neutral Ocean, Neutral Amethyst and Neutral Amber, pairing Neutral node backgrounds and titles with each palette's colored controls. Eclipse's Theme groups option applies matching Neutral group colors.
- **Docs**
  - Document the new variants, linked selection across the Nova packs and group appearance.
- **Changed files**
  - .defaults/themes/neutral-jade.json.example
  - .defaults/themes/neutral-ocean.json.example
  - .defaults/themes/neutral-amethyst.json.example
  - .defaults/themes/neutral-amber.json.example
  - Readme/Node_Design.md
  - README.md
  - Readme/README.md
  - pyproject.toml

### Version: 1.0.2

- **Fix**
  - Preserve conditioning attention masks in IO Slice & Dice and list/batch conversion, including single-image selections and shared masks.
- **Changed files**
  - core/batch_helpers.py
  - pyproject.toml

### Version: 1.0.1

- **Fix**
  - Preserve category title colors for pipe, router and Get/Set nodes when applying themes or reopening workflows. Previously automatic gray titles return to their category color; custom title colors remain unchanged.
- **Changed files**
  - js/node-design-theme.js
  - pyproject.toml

## 2026-10-17

### Version: 1.0.0

**Initial release of Eclipse Nova**

Eclipse Nova 1.0.0 is the initial release of a separate repository, built from
the original Eclipse pack with a redesigned frontend. This entry describes the
features and improvements included in that first release.

Canvas performance was a major reason for the move from Eclipse to Nova:
large workflows made the cost and complexity of managing many widgets
particularly noticeable. This release focuses on reducing that overhead and
making complex nodes easier to use in both classic canvas and Nodes 2.0.

The design and panel-based approach are inspired by the DaSiWa node set and
adapted to Nova's tools and workflows.

- **Design and usability**
  - Redesigned nodes use compact panels with structured configuration, replacing the earlier approach of managing large sets of individual widgets through visibility helpers.
  - Shared controls provide collapsible mode bars, pinnable sections, searchable menus, dynamic rows, color pickers and resizable text/media areas, adapted to each tool's purpose.
  - Use Sliders adds live sliders to bounded numeric fields in the redesigned panels while retaining exact number entry and seed precision.
  - Neutral is the default node design for new installations, with gray controls and no selection glow. Saved theme choices remain unchanged.
  - Editable JSON themes provide Jade, Neutral, Ocean, Amethyst and warm Amber (matching the README tour) plus user designs in themes/custom. Appearance settings apply colors to controls and backgrounds, including inside subgraphs.
  - Automatic titles use the theme's +20 gray offset and follow the selected design through workflow loads, including missing or older automatic title colors. Custom titles and black routing bodies are preserved.
  - Theme regular nodes and Theme groups are independent Appearance options, both off by default. Group colors use RGB 60 with dark themes and RGB 80 with Neutral. Turning either option off restores previous colors, including after a workflow reload.
  - Link Nova themes optionally keeps installed SmartLLM Nova and Smart Model Loader Nova packs on Eclipse's selected theme across changes and restarts. Each pack saves its own preference; unlinking restores independent choices. Missing custom themes or failed saves are reported without substituting another theme.
  - Bundled themes are extracted once from .defaults/themes into the user-owned themes folder. Existing palettes, custom edits and deleted files are preserved across restarts and updates; a newly bundled theme is installed once.
  - Panel values and layout choices persist through workflow saves, reloads and renderer changes.
  - Text editors share the available node space between open fields. A single visible field fills the space, and dragging a field's resize handle adjusts the split while preserving the outer node size.
  - Fixed-input processing and utility tools use the shared design as their standard interface, with flat controls for small operations and conditional sections for more complex settings.
- **Canvas performance**
  - The new panels use localized updates driven by edits, lifecycle events and content-size changes. Size measurements are batched, and unchanged dimensions do not trigger another resize.
  - The old widget-visibility and system-performance helper layers, global preview/viewport culling and resize patches are removed. The redesigned interfaces handle their own layout through ComfyUI's DOM hosting.
  - Prompt-library catalog and file reads are shared during workflow loading and page refreshes, avoiding duplicate requests when many prompt nodes use the same files.
  - Shared appearance loads once at startup and updates on explicit changes, without per-node polling or draw-time color checks. Retired frontend scripts and duplicate interfaces are excluded from the initial release.
- **Workflow experience**
  - Shared seed controls preserve exact 64-bit values and support local or connected seeds where applicable. Partial execution scopes seed advancement and automatic choices to the requested workflow branch.
  - Play actions use ComfyUI's native execution up to the selected node. Review controls can pause changed results while unchanged cached inputs continue.
  - SEGS Preview Simple passes its input through the first SEGS output, with IMAGE second, so downstream SEGS processing can include the preview in its execution path.
  - Detailer uses Eclipse's final-image grid with click-to-next browsing and a shared area for live sampling previews. Preview immediately hides or restores available images without another queue, and the preview area resizes in both renderers.
  - Image Filter Adjustments Advanced responds to Interrupt/Cancel during resizing and supersampling. It computes supersampled regions on demand instead of allocating the whole enlarged intermediate, preserves the selected scale and filter, and checks available RAM before allocating large outputs.
  - Image Selector keeps the seeds used for the displayed results when continuing with Nova prompt, sampler and companion panels. Confirmation is tied to every image's contents, including changes within a batch.
  - Image uploads respect the shared mutation restrictions and reserve separate filenames for simultaneous uploads.
  - Dedicated override inputs and optional settings pipes connect compact editors to larger workflows. A pipe-priority toggle lets supplied sampler settings and seeds override local controls while retaining local values for missing settings. Searchable file browsers, generation metadata and resizable previews support inspection and reuse of results.
  - Processing panels retain existing data and list contracts, expose connected setting overrides, and make execution reports available beside their controls. Model choices refresh on demand.
  - Related tools are consolidated where they share a purpose, with reusable processing engines and UI components supporting a smaller, more consistent interface.
- **Independent Nova release**
  - Nova has its own node IDs, menu, settings, API routes and configuration, allowing installation alongside the original Eclipse pack.
  - Linux CFFI startup compatibility is retained.
  - Nova exposes its prompt library through smart_prompt_nova. The original Eclipse wildcard link is preserved, and Nova ignores stale links from removed or disabled checkouts.
  - The README and node guides describe the available tools and their usage, with a visual-tour index and annotated screenshots of the current panels, themes and routing dialogs.

- **Fix**

  These fixes address issues carried over from the original Eclipse repository
  and are included in Nova's initial release.

  - Keep primitive conversion, switch and pipe links scoped to their owning graph, including nested workflows and restored typed connections.
  - Evaluate all 64 lazy-switch slots in priority order, fall through resolved empty results, preserve zero and false values, and skip unused branches. Saved high-slot connections survive workflow loading while fresh nodes show only active rows.
  - Preserve separate prompts, every conditioning entry, pooled outputs and masks when converting or selecting batches. Conditioning from encoders without pooled embeddings remains valid. Compatible prompts batch along the sample axis; incompatible dimensions or metadata produce clear errors.
  - Preserve latent metadata, noise masks and batch indices through list/batch conversion, including broadcast masks, mixed masked and unmasked samples, and matching video batches. Small-width masks retain their batch axis.
  - Keep scalar pipe values whole, retain enabled zero-valued generation settings, and keep Slice & Dice conditioning aligned with selected images and text.
  - Reject impossible Image Align Size Shrink requests with Grow/Resize guidance, keep reported image and mask dimensions consistent, and assign cumulative SEGS frame indices across mask batches.
  - Preserve selected newline delimiters in Join and Merge Strings, and preserve floating-point frame data when Frame Consistency effects are disabled.
