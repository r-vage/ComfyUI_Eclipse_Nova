# Changelog

## 2026-11-08

### Version: 1.0.30

- **Feat (New)**
  - Add Part Prompt Editor to read combined prompts and time ranges from the existing saved-run selection, edit individual render parts, and apply full prompt replacements on Resume for lip-sync or native H3. Route it through Get/Set into subgraphs without loading models or media arrays to review text.
- **Feat**
  - Save prompt corrections in the new run revision, including upcoming parts, while preserving timing, references, audio, warmup and retained media. Keep changes local to the selected render part even when a scene spans several renders. Validate the source run and restart position before creating a revision; provide Apply, Reset and Clear controls.
- **Fix**
  - Align Preview Video soundtracks from input sample zero for image batches and frame timelines. Remove the extra AAC packet delay so preview audio timing agrees with final exports.
- **Docs**
  - Explain per-part prompt correction, full replacement text, restart selection and continuing an edited revision.
- **Changed files**
  - core/minimax_h3_prompts.py
  - core/minimax_h3_segmented_conditioning.py
  - core/server_endpoints.py
  - core/video_checkpoint.py
  - core/video_part_prompts.py
  - core/video_preview.py
  - js/eclipse-part-prompts.js
  - py/RvVideo_PartPromptEditor.py
  - py/RvVideo_Resume.py
  - pyproject.toml
  - README.md
  - Readme/README.md
  - Readme/Frame_Timeline.md
  - Readme/Loops.md

### Version: 1.0.29

- **Feat (New)**
  - Add Video Run Storage for CPU RAM, temporary disk or persistent output. Share the control across frame timelines, native video clip accumulation and scene-analysis image caching, preserving temporary storage for existing connections.
  - Add Load Video Run to restore ordered video parts, exact frame ranges, FPS, dimensions and saved soundtracks after a restart. Use one refreshable dropdown to select discovered output runs. Write a manifest after each completed part, keep workflow/prompt snapshots when available, and support moving the whole run folder with relative part paths. Unavailable inactive selections do not block New run; Load and Resume require an available selected run.
  - Add Video Run Gate to skip independent generation outputs without requesting their upstream inputs and pass through absent or muted optional sources. Add Video Run Info for selected-media timing, storage size and retained-part ranges.
  - Add Eclipse-owned Loop Start, Video Loop Start and Loop End for sequential analysis and H3 rendering without Easy-Use. Support loops inside subgraphs, with stop requests scoped to the matching loop. Limit parts per queue or stop after saving the current part and its accumulated preview, preserving warmup-trim and transition review. Load mode skips fresh inputs and rendering, including independent accumulated previews.
  - Add Loop Control to place the live Stop after current part button outside a subgraph. Connect it to either loop start through Get/Set; synchronize both buttons and keep requests scoped to the current queue.
  - Save resolved timing plans, prompts, references, canvas and audio in persistent render checkpoints, including the full caption recording and excerpt start. Resume without fresh analysis or planning, continue after completed parts or replace from a selected part in a new revision. Keep original media unchanged; retain load/export for older media-only runs. Expose the matching caption context on loop completion or loading so captions align with the saved excerpt.
  - Add Video Part Seed to separate absolute clip selection from sampling variation and record each completed part's actual seed.
- **Feat**
  - Add an optional enable input to Load Audio to skip source loading and previews during saved-run recovery.
  - Let IO Lyric Captions use generated VIDEO audio when no separate recording is supplied, including RAM clips without concatenating their pixels.
- **Fix**
  - Preserve soundtrack timing when exporting image batches and frame timelines to MP4. Set audio timestamps so AAC encoder priming does not introduce a one-packet playback delay.
  - Rebuild Load Video temporary outputs and scene-analysis sample caches when their files are removed between queues. Invalidate the affected producer and dependent outputs while preserving reuse of intact media, independent workflow variants and downstream-only edits.
  - Return the original VIDEO through Preview Video while retaining its viewing copy separately. Preserve native loop state and its storage metadata instead of feeding a compressed preview back into accumulation.
- **Docs**
  - Explain RAM and disk resource use, saved-run ownership, downstream re-export, analysis cache behavior and the limits of media checkpoints.
  - Document loop wiring, New/Resume/Load controls, saved input recovery, accumulated previews and separate preparation/render gates.
- **Changed files**
  - core/cache_artifacts.py
  - core/execution_cache.py
  - core/frame_timeline.py
  - core/loop.py
  - core/lyric_caption_pipe.py
  - core/scene_analysis.py
  - core/seed_cache.py
  - core/server_endpoints.py
  - core/video_checkpoint.py
  - core/video_clip_append.py
  - core/video_preview.py
  - core/video_resume.py
  - core/video_run.py
  - core/video_saving.py
  - core/video_stream.py
  - js/eclipse-loop.js
  - js/eclipse-video-run.js
  - py/RvLogic_Loop.py
  - py/RvLogic_LoopControl.py
  - py/RvAudio_LoadAudio.py
  - py/RvVideo_AppendClip.py
  - py/RvVideo_FrameTimeline.py
  - py/RvVideo_Load.py
  - py/RvVideo_Resume.py
  - py/RvVideo_RunStorage.py
  - py/RvVideo_SceneAnalysis.py
  - pyproject.toml
  - README.md
  - Readme/README.md
  - Readme/Frame_Timeline.md
  - Readme/Load_Video.md
  - Readme/Load_Audio.md
  - Readme/Lyric_Captions.md
  - Readme/Loops.md
  - Readme/MiniMax_H3_Clips.md
  - Readme/Scene_Analysis.md

## 2026-11-07

### Version: 1.0.28

- **Feat**
  - Add native MiniMax H3 clip planning and conditioning for text, visual references or first/last images, with loaded audio, reference audio and generated audio in priority order. Preserve source duration and cut timing, retain last-image guides before discarded padding, and reuse Load Image Timeline's resized batch. Select native visual references without fixed endpoints, text-only conditioning, or a starting image per scene. Untimed scene prompts share the duration evenly; capacity splits retain their scene prompt and image assignment.
  - Add Append Video Clip to retain generated video and audio on disk across loops, with an optional original soundtrack for the assembled VIDEO. Preserve whether Load Video's sources contain unmuted audio so synthesized silence permits generated-audio fallback.
  - Add CPU scene detection with measured source timing, disk-backed frame sampling, bounded overlapping windows and text-only loop collection for reference-video performance analysis.
  - Validate and save structured scene motion observations and sampled-frame evidence. Scene Analysis to H3 exposes separate global, first-part and subsequent-part prompts; Segmented Conditioning applies only the active part. Use these final node names as the sole interfaces, without temporary duplicates or embedded opening-scope text. Give each part one continuous-shot prompt with measured cuts applied during joining; keep timing/audio mechanics in the planner and prevent opening poses from leaking into later parts.
  - Export concise performance paragraphs written alongside observations in the same analysis call. Accept motion-only results without appearance metadata and full T2V descriptions with appearance. Preserve new task paragraphs and edited directions without appearance rewriting, and require matching export policy. Older unmarked version-2 analyses retain bounded clothing/background and routine mouth-sentence cleanup. Retain black scenes and measured timing; reject analyses without performance paragraphs.
  - Add an optional Scene Cut Limit after detection to enforce measured-time spacing without moving retained cuts or rescanning. Record excluded edits in window context so they are not mistaken for motion. Add an appearance dropdown to the H3 adapter to select motion-only image animation or full text-to-video descriptions.
- **Fix**
  - Keep Compact IDs stable when dynamic nodes reorder link records during reload. Preserve connection and reroute ordering while retaining validation and rollback for broken links.
  - Keep usable scene descriptions with review warnings when they include unwanted appearance or questionable pose wording. Preserve the text in saved analyses and H3 outputs for copying and manual editing, including cached content rejections. Accept scalar action, gaze/expression and uncertainty text as list entries without rewording. Treat T2V appearance audits as optional metadata, retaining unusual formats for review without blocking the complete generation paragraph; stop only for broken required structure or incomplete coverage.
  - Split multiline H3 cut instructions into individual shot directions, including joined analysis output and connected lists. Prevent every scene receiving the complete prompt sequence, and show the direction count in the planner report while preserving cut timing and audio ranges.
- **Docs**
  - Document native H3 clip connections, optional references and soundtrack selection. Clarify that image-slot blends affect the still-image renderer and do not automatically fade generated clips.
  - Add practical tooltips to every scene-analysis input and output, covering detection sensitivity, independent resolutions, sample budgets, per-request frame limits, overlap, loop wiring, cut spacing and task-specific H3 export.
  - Document node connections for optional live analysis, editable manual inputs and saved-analysis reuse. Keep each source's timings and part prompts together through Set/Get routing, with the global performance prompt independent of part-source muting.
  - Update the README and guides for scene analysis, current image controls and part prompts. Remove references to unshipped workflows while retaining the bundled Get All Active shared-chain preview.
- **Changed files**
  - README.md
  - Readme/README.md
  - Readme/Character_Reference_Nodes.md
  - Readme/Character_Shot_Planner.md
  - Readme/GetFirst_GetAllActive.md
  - Readme/Load_Audio.md
  - Readme/MiniMax_H3_Audio_Planner.md
  - Readme/MiniMax_H3_Clips.md
  - Readme/Image_Timeline_Video.md
  - Readme/Operation_Panels.md
  - Readme/Scene_Analysis.md
  - core/minimax_h3_segmented_conditioning.py
  - core/minimax_h3_segmented_timeline.py
  - core/minimax_h3_clips.py
  - core/video_clip_append.py
  - core/video_loader.py
  - core/scene_analysis.py
  - core/scene_motion_text.py
  - js/eclipse-workflow-id-utils.js
  - py/RvVideo_MiniMaxH3Panels.py
  - py/RvVideo_MiniMaxH3Clips.py
  - py/RvVideo_AppendClip.py
  - py/RvVideo_SceneAnalysis.py
  - pyproject.toml
  - requirements.txt

## 2026-11-05

### Version: 1.0.27

- **Feat**
  - Support manually timed MiniMax H3 camera cuts from one source image. Keep cuts on the native 24 FPS timeline and preserve continuous original audio through hidden warmups and direct stitching.
  - Apply each cut's framing and animation instructions to its following shot, retaining that direction across extra capacity splits. Report manual camera cuts separately from image transitions and reject invalid or duplicate frame times.
- **Changed files**
  - core/minimax_h3_configuration.py
  - core/minimax_h3_segment_plan.py
  - core/minimax_h3_segmented_timeline.py
  - js/eclipse-minimax-form.js
  - Readme/MiniMax_H3_Audio_Planner.md
  - pyproject.toml

## 2026-11-01

### Version: 1.0.26

- **Feat**
  - Add a collapsible Presets bar below Options in Eclipse KSampler Advanced. Save, search, load, overwrite and delete named configurations for every mode, including both stages, latent upscale and optional guidance. Keep seeds and output preferences local, and retain the bar state in saved workflows.
  - Bundle Moss J1b_v2 and Moss Moody_v2.2 sampler presets and extract each once at startup, preserving existing presets and subsequent edits or deletions.
- **Changed files**
  - .defaults/presets/samplers/Moss J1b_v2.json.example
  - .defaults/presets/samplers/Moss Moody_v2.2.json.example
  - core/default_files.py
  - core/migration.py
  - core/sampler_configuration.py
  - core/sampler_presets.py
  - core/server_endpoints.py
  - core/theme_defaults.py
  - js/eclipse-panel.css
  - js/eclipse-sampler-form.js
  - js/eclipse-sampler-presets.js
  - js/eclipse-sampler-state.js
  - js/eclipse-sampler.js
  - Readme/Advanced_Sampler.md
  - pyproject.toml

## 2026-10-31

### Version: 1.0.25

- **Fix**
  - Preserve Anima's T5 token IDs and weights in IO Slice & Dice and conditioning list/batch conversion. Keep complete token vectors aligned with selected positive and negative prompts, including repeated selections, while rejecting incompatible prompts during batch conversion.
- **Changed files**
  - core/batch_helpers.py
  - pyproject.toml

## 2026-10-29

### Version: 1.0.24

- **Fix**
  - Restore middle-button canvas panning over sampler previews, Smart Prompt and shared Nova panels. Forward wheel navigation over live previews as well as completed images, while preserving control editing and focused text scrolling in classic canvas and Nodes 2.0.
  - Keep the last valid sampler preview visible until its replacement has decoded. Bound pending frames, release image URLs after replacement, and discard late frames after completion, interruption or node removal.
- **Changed files**
  - js/eclipse-configuration-panel.js
  - js/eclipse-detailer-preview.js
  - js/eclipse-dom-preview.js
  - js/eclipse-sampler.js
  - js/eclipse-smart-prompt.js
  - js/eclipse-widget-utils.js
  - pyproject.toml

## 2026-10-29

### Version: 1.0.23

- **Feat**
  - Extend Detailer (Advanced) Color match with Wavelet, Reinhard LAB and ScatterSort, sharing all nine methods with Image Filter Adjustments. Wavelet preserves spatial detail while matching tones within the region mask. Retain adjustable strength, neutral grayscale, alpha and unchanged pixels outside the region; use ComfyUI's configured device for the added methods.
- **Fix**
  - Default Tiled encode and Tiled decode to off in both detailers to avoid VAE tiling color shifts unless explicitly enabled. Preserve saved workflow selections.
- **Changed files**
  - core/detailer_color_match.py
  - core/detailer_configuration.py
  - core/image_adjustments_configuration.py
  - core/image_color_match.py
  - core/sampler_configuration.py
  - Readme/Integrated_Detailer.md
  - pyproject.toml

## 2026-10-28

### Version: 1.0.22

- **Feat (New)**
  - Add optional Color match to the Detailer (Advanced) Mode bar, revealing a settings section with six methods and adjustable strength. Match each decoded region to its original masked pixels before feathered compositing, reducing color and tonal shifts while retaining sampled detail, alpha and per-image ownership. Keep neutral black-and-white regions neutral, include corrected crops in output SEGS, and preserve existing workflows with correction disabled by default.
- **Refactor**
  - Simplify Detailer (Advanced): hide Sampler while Use pipe settings is enabled, retain local fallback values and keep Cycles available under Sizing. Remove the bottom sampling preview and its button while retaining sampling progress and both detection/segmentation review sections with their Stop buttons. Accept older saved preview settings without re-enabling the removed preview.
- **Changed files**
  - core/detailer_color_match.py
  - core/detailer_configuration.py
  - core/detailer_execution.py
  - extern/impact/impact_pack.py
  - js/eclipse-detailer-form.js
  - js/eclipse-detailer-preview.js
  - js/eclipse-sampler-form.js
  - js/eclipse-sampler-state.js
  - js/eclipse-sampler.js
  - py/RvSampler_DetailerIntegrated.py
  - Readme/Integrated_Detailer.md
  - pyproject.toml

## 2026-10-28

### Version: 1.0.21

- **Feat (New)**
  - Add a theme editor to Eclipse Nova's Appearance settings, with color pickers, opacity, shadow layers and the remaining template fields. Preview edits before applying them; Save updates the selected theme through a custom override, while Save As creates a separate theme. Preserve bundled files and manual node colors, retain unsaved drafts after errors, and protect against conflicting edits.
- **Changed files**
  - core/server_endpoints.py
  - core/theme_editor.py
  - js/eclipse-node-design.js
  - js/eclipse-theme-editor.js
  - js/eclipse-theme-editor.css
  - js/eclipse-theme-editor-controls.js
  - js/eclipse-theme-editor-form.js
  - js/node-design-theme.js
  - README.md
  - Readme/README.md
  - Readme/Node_Design.md
  - pyproject.toml

## 2026-10-27

### Version: 1.0.20

- **Feat (New)**
  - Add Detailer (Advanced), an integrated image/pipe detailer, and a compact IO Detailer compatible with IO KSampler. Use external SEGS/boxes or internal YOLO, with one model selector scanning both bbox/segm folders and automatic detection of the checkpoint's type. Include detection-label filtering, per-image region selection, independent SAM2 and edge refinement, and grow/blur. Review selected boxes and final masks in separate collapsible previews with independent Stop controls; requeue unchanged to continue without consuming sampling seeds or caching partial image outputs. Keep reviews and completed results independent for each node, including copies with identical inputs. Support standard YOLO architectures, including nested YOLO9/11/12 blocks and older checkpoints retaining training-loss or Dill-serialized module state, with restricted loading and clear diagnostics for classification or unsupported files. Use ComfyUI’s configured default accelerator or CPU, retaining saved device selections and correct model offloading. Release detection/matting models before diffusion detailing; expose prepared masks/SEGS through the pipe while preserving initial generation metadata. Accept externally encoded positive/negative conditioning lists for labeled SEGS, preserving text-encoder weighting and guidance, plus shared or category-specific denoise values through the existing IO input. Combine paired regions within each category and let internal YOLO use the first conditioning pair and denoise value. Retain the original Detailer.
- **Fix**
  - Standardize compute-device choices on Default and CPU, retaining older workflow selections. Use ComfyUI's configured accelerator consistently for placement and memory reservations in transcription and Qwen word timing; use CPU for Whisper on unsupported accelerator backends. Keep image resize, mask crop and video upscale aligned with the same device policy.
  - Keep both detailers stable when live or review previews update during execution. Release temporary height when sections collapse or review previews shrink, while retaining the user's width, chosen height and independently resized review previews across workflow reloads.
  - Allow String Multiline's Text and Result fields to shrink to one visible line, retaining scrolling, adjustable space sharing and saved node sizes.
- **Refactor**
  - Keep SEGS detailer previews focused on live sampling, removing the separate final-image preview and temporary image writes. Preserve completed image outputs and the integrated detection/segmentation review sections.
- **Changed files**
  - core/devices.py
  - core/operation_panel.py
  - core/operation_panel_layouts.py
  - core/resize_configuration.py
  - core/lyric_caption_configuration.py
  - core/lyric_alignment.py
  - core/lyric_qwen.py
  - core/image_crop_by_mask.py
  - core/image_resize.py
  - core/media_tool_configuration.py
  - core/video_upscale.py
  - js/eclipse-operation-state.js
  - js/eclipse-caption-state.js
  - js/eclipse-media-tool-state.js
  - js/eclipse-resize-state.js
  - js/eclipse-resize-form.js
  - core/detailer_configuration.py
  - core/detailer_matting.py
  - core/detailer_models.py
  - core/detailer_pipe.py
  - core/detailer_conditioning.py
  - core/detailer_regions.py
  - core/detailer_review.py
  - core/sampler_configuration.py
  - core/seg_masks.py
  - js/eclipse-detailer-form.js
  - js/eclipse-detailer-preview.js
  - js/eclipse-detailer-review.js
  - js/eclipse-multiline-panel.js
  - js/eclipse-panel-text-layout.js
  - js/eclipse-panel.css
  - js/eclipse-sampler-form.js
  - js/eclipse-sampler-queue.js
  - js/eclipse-sampler-state.js
  - js/eclipse-sampler.js
  - py/RvMask_ToSEGS.py
  - py/RvPipe_IO_Detailer.py
  - py/RvSampler_DetailerForEach.py
  - py/RvSampler_DetailerIntegrated.py
  - requirements-detailer.txt
  - pyproject.toml
  - README.md
  - Readme/Integrated_Detailer.md
  - Readme/README.md
  - Readme/Sampler.md

## 2026-10-25

### Version: 1.0.19

- **Fix**
  - Remove type-based node recoloring, including forced black colors on Float and routing nodes. Preserve custom titles and backgrounds across theme changes and workflow reloads, including in subgraphs, while keeping themed controls and untouched defaults.
  - Support Krea2 and Qwen Image single-frame latents in the advanced sampler's between-stage upscale, preserving batch, channel and frame dimensions.
  - Support a lower-denoise second pass in Eclipse KSampler Advanced, including IO KSampler control and generation metadata. Apply Stage 2 Denoise when Start step is zero, retain full-schedule continuation otherwise, and preserve existing configurations and socket indices.
  - Let To Batch resize single-frame 5D latents while preserving latent values and channel counts. Keep noise masks aligned with the spatial crop and retain validation for mismatched video latents.
  - Use full-resolution originals for Image Selector's Open, Save, Copy, Clipspace and Mask Editor actions while keeping lightweight canvas thumbnails. Preserve original alpha and workflow metadata, reuse files after confirmation, and clean them up with the grid.
  - Clear Image Comparer's saved previews, pair numbers and image actions when temporary images expire. Keep its settings and size, prevent late image errors from clearing newer results, and restore navigation on the next execution.
- **Changed files**
  - core/advanced_sampler.py
  - core/batch_helpers.py
  - core/image_selection.py
  - core/sampler_configuration.py
  - js/eclipse-image-selector.js
  - js/eclipse-image-review-panel.js
  - js/eclipse-node-design.js
  - js/eclipse-sampler-form.js
  - js/eclipse-sampler-state.js
  - js/eclipse-selector-image-actions.js
  - js/node-design-theme.js
  - py/RvSampler_KSamplerAdvanced.py
  - README.md
  - Readme/Advanced_Sampler.md
  - Readme/Image_Review.md
  - Readme/README.md
  - Readme/Node_Design.md
  - pyproject.toml

## 2026-10-25

### Version: 1.0.18

- **Fix**
  - Make Load Image Timeline's images output a single batch at the resolved canvas size, applying each enabled slot's fit and crop alignment without blending or video effects. Preserve slot order and alpha, while keeping original images and per-image settings in the PIPE for timeline rendering.
- **Changed files**
  - core/image_timeline_loader.py
  - core/image_timeline_video.py
  - py/RvImage_LoadImageTimeline.py
  - Readme/Image_Timeline_Video.md
  - pyproject.toml

## 2026-10-25

### Version: 1.0.17

- **Feat**
  - Add per-slot video overlays to Load Video with stable target selection, opacity, time offsets, Screen blending, black-background removal, embedded alpha and separate mask videos. Preserve the base clip's duration and soundtrack, align different frame rates, and include layers in previews, progress and cache reuse. Existing slots remain sequential.
  - Add a source frame/time readout, direct seconds seeking, frame stepping and Set start here to Load Video. Choose trims visually without queueing or rebuilding, retain each slot's load cap, and identify FPS-based frame estimates for variable-rate sources.
- **Changed files**
  - core/video_overlays.py
  - core/video_loader.py
  - core/server_endpoints.py
  - py/RvVideo_Load.py
  - js/eclipse-video-overlays.js
  - js/eclipse-video-source-position.js
  - js/eclipse-video-slots.js
  - js/eclipse-video-playlist.js
  - js/eclipse-video-panel.js
  - js/eclipse-panel.css
  - Readme/Load_Video.md
  - pyproject.toml

## 2026-10-25

### Version: 1.0.16

- **Fix**
  - Refine Load Video and Load Image Timeline layouts with compact borderless controls, easier dragging, consistent spacing and thinner focus borders. Keep video slot summaries visible with fit and per-clip blend modes, remove misleading filename arrows, and adapt the video browser grid to thumbnail aspect ratios.
  - Show Load Video preview-build progress while retaining native progress for queued builds, completing only after file finalization. Reuse matching previews, avoid duplicate simultaneous encodes, and clear cancelled or failed progress without stale responses replacing queued output.
- **Changed files**
  - js/eclipse-video-slots.js
  - js/eclipse-video-panel.js
  - js/eclipse-video-playlist.js
  - js/eclipse-video-browser.js
  - js/eclipse-panel.css
  - js/eclipse-image-timeline-form.js
  - js/eclipse-image-timeline.css
  - core/video_timing.py
  - core/video_loader.py
  - core/server_endpoints.py
  - Readme/Load_Video.md
  - pyproject.toml

## 2026-10-24

### Version: 1.0.15

- **Fix**
  - Keep generation-data pipes aligned with selected images by adding an optional PIPE input/output to IO Slice & Dice. Map each selection to its source sampler batch, preserve selection order across reruns, and reject ambiguous batch counts. Document selecting sampler settings alongside prompts to prevent mismatched save counts or metadata repeated from unrelated images.
- **Changed files**
  - core/selection_metadata.py
  - py/RvPipe_IO_SliceDice.py
  - Readme/Batch_Selection_Slice_Dice.md
  - Readme/Save_Images.md
  - pyproject.toml

## 2026-10-24

### Version: 1.0.14

- **Feat**
  - Add Max words to both lyric-caption panels for Whole line, Active word, Float lines and Rotate lines. Show long lines as successive phrases using existing word timings, preserving active-word highlighting and phrase boundaries across trims. Zero keeps complete lines in existing workflows; original lyrics, SRT and timing JSON remain available for correction and reuse.
- **Changed files**
  - core/lyric_animation.py
  - core/lyric_caption_configuration.py
  - core/lyric_captions.py
  - core/lyric_render.py
  - js/eclipse-caption-form.js
  - js/eclipse-caption-state.js
  - Readme/Lyric_Captions.md
  - pyproject.toml

## 2026-10-23

### Version: 1.0.13

- **Fix**
  - Preserve Image Selector's mounted previews, selection order and scroll position when confirming or receiving unchanged cached results, avoiding a visible grid reload during Continue.
  - Let Preview Video reuse unchanged inputs with Stop enabled or disabled. Prevent previews from invalidating downstream sampling loops on every queue, allowing cached generation to remain available for downstream caption styling and export changes. Changed inputs still update the preview and trigger Stop review when enabled.
  - Cache Read Prompt Files and Load Files From Folder (Single mode) when an unchanged connected seed freezes selection. Preserve automatic advancement without a seed, Step-mode advancement and detection of changed source files.
  - Cache Kargim, KSampler Advanced, SEGS Detailer and PIPE lyric-caption rendering when a supplied seed overrides local Random. Preserve random fallback for missing or None seeds and disabled sampler overrides. Handle sampler PIPE lists mixing supplied and local seeds without UI aggregation errors.
- **Changed files**
  - js/eclipse-image-selector.js
  - core/seed_cache.py
  - py/RvImage_LoadFiles.py
  - py/RvSampler_DetailerForEach.py
  - py/RvSampler_KSamplerAdvanced.py
  - py/RvSampler_KSamplerKargim.py
  - py/RvText_ReadPromptFiles.py
  - py/RvVideo_Preview.py
  - py/RvVideo_RenderLyricCaptionsPipe.py
  - Readme/Frame_Timeline.md
  - pyproject.toml

## 2026-10-23

### Version: 1.0.12

- **Docs**
  - Refresh the Load Video visual tour with per-clip blends, shared blending, Global style and a rendered joined preview. Remove the outdated hard-joins-only limitation.
  - Add an annotated Load Image Timeline tour covering image slots, crop previews, per-image transitions, selected generation metadata and the connected PIPE flow into IO Image Timeline and its renderer. Link the scenes from the main visual tour and identify their capture versions.
- **Changed files**
  - Readme/Visual_Tour.md
  - Readme/Load_Video.md
  - Readme/Image_Timeline_Video.md
  - Readme/assets/nova-load-video.png
  - Readme/assets/nova-load-image-timeline.png
  - Readme/assets/nova-load-image-timeline-metadata.png
  - Readme/assets/nova-load-image-timeline-pipe.png
  - pyproject.toml

## 2026-10-23

### Version: 1.0.11

- **Feat (New)**
  - Add PIPE-only Image Timeline Video and IO Image Timeline to hold one image for the soundtrack's duration or switch multiple images using even spacing, nearby quiet gaps or manual times. Share Wan/MiniMax activity-gap detection and Batch Extend With Overlap's visual blends, including CPU optical-flow morphs with reusable motion estimation, shared size/FPS overrides and a visible report. Stream a lossless temporary VIDEO with the original soundtrack for captions or saving, preserving audio timing without allocating a full decoded video batch.
  - Add Load Image Timeline with reorderable file slots, multi-file drag-and-drop, centered cropping and per-image blends that override renderer defaults. Scroll the file list without canvas zoom. A shared Update previews button refreshes every crop locally or resolves optional width/height inputs through one partial run ending at the loader, with each dimension's source shown. Choose one image's sampler, prompt and seed metadata for downstream PIPE use; preserve per-image options when unchanged images pass through IO and retain the Image Selector route.
- **Feat**
  - Add Save Video's Audio input toggle to replace native VIDEO soundtracks with connected audio while preserving video duration, frame timing and crop/trim. Trim excess audio, pad shorter tracks with silence, and return the saved VIDEO with the same soundtrack as its preview. Existing workflows keep the override off.
  - Share ghost zoom, flash/light leak, block glitch, zoom blur and dip-to-black transitions across image timelines, Load Video and Batch Extend With Overlap. Load Video adds global defaults and per-clip overrides to its joined preview and output, preserving clip timing, audio and metadata.
  - Add a Global style section to Image Timeline Video and Load Video for whole-sequence colour grading and repeating effects, including combined Black pulse flash, Ghost edit and Glitch edit styles with strength and period controls. Stream effects without retaining full video batches; existing workflows keep styling off.
- **Fix**
  - Keep mouse-wheel scrolling inside Load Video's clip list in Nodes 2.0, including at its top and bottom, while retaining normal canvas zoom outside the list.
  - Convert native VIDEO previews to browser-compatible H.264 with AAC audio instead of remuxing lossless RGB streams, preventing green/magenta playback from image timelines and video upscaling. Preserve source timing and reuse already compatible Eclipse previews.
- **Docs**
  - Document both image timeline sources, PIPE connections, framing, per-image/clip blending, global styles, metadata selection and connections to lyric captions and saving.

- **Changed files**
  - core/video_audio.py
  - core/video_saving.py
  - core/save_video_configuration.py
  - py/RvVideo_SaveData.py
  - js/eclipse-save-video-state.js
  - js/eclipse-save-video-form.js
  - Readme/Save_Video_Data.md
  - Readme/Lyric_Captions.md
  - core/audio_timeline.py
  - core/image_timeline_video.py
  - core/image_timeline_pipe.py
  - core/image_timeline_loader.py
  - core/image_blending.py
  - core/image_morph.py
  - core/image_effects.py
  - core/video_transitions.py
  - core/video_panel_configuration.py
  - core/server_endpoints.py
  - core/operation_panel.py
  - core/video_loader.py
  - py/RvImage_BatchExtendWithOverlap.py
  - py/RvImage_LoadImageTimeline.py
  - py/RvPipe_IO_ImageTimeline.py
  - js/eclipse-image-timeline-state.js
  - js/eclipse-image-timeline-form.js
  - js/eclipse-image-timeline-panel.js
  - js/eclipse-image-timeline.css
  - js/eclipse-panel-run.js
  - js/eclipse-widget-utils.js
  - js/eclipse-video-slots.js
  - js/eclipse-video-playlist.js
  - js/eclipse-video-panel.js
  - js/eclipse-operation-state.js
  - js/eclipse-panel.css
  - core/video_helpers.py
  - core/operation_panel_layouts.py
  - py/RvVideo_ImageTimeline.py
  - py/RvVideo_Load.py
  - Readme/Image_Timeline_Video.md
  - Readme/Load_Video.md
  - Readme/README.md
  - pyproject.toml

## 2026-10-23

### Version: 1.0.10

- **Feat (New)**
  - Add Render Lyric Captions_v2 with PIPE-only input/output and compact IO Lyric Captions for original audio, vocals, lyrics/timing, separate manual corrections, background, dimensions, FPS, trim and seed. Keep appearance and alignment choices local to each renderer. Return the used settings and full-song timing alongside video, SRT and report; retain the existing renderer.
  - Add WAN LipSync Conditioning, using native InfiniteTalk with an explicit audio start and a bounded motion tail. Plan Step accepts IMAGE batches or disk-backed timelines; the disk path preserves the full audio clock at 25 FPS without keeping all preceding frames in RAM.
- **Feat**
  - Add optional Qwen3 forced alignment to Transcribe Audio and both lyric renderers, with a compare-only mode, bounded phrase timing and cached reuse. Download missing official model files on first use, verify the pinned revision and reuse local files offline. Keep Whisper large-v3 as the default and preserve manual timing priority; invalid Qwen estimates retain existing phrase timing.
  - Add Play to Preview Video's Mode bar to run its upstream branch through the preview without starting downstream work or changing Stop. Play remains available when collapsed; existing review and cancel controls are retained.
  - Share transcription and bounded reference caches between Transcribe Audio and the new pipe renderer. Empty corrections keep original timing; recognizable wording edits align only changed phrases while preserving unchanged lines, and populated manual timing takes priority. Preview and final renders can reuse the same resolved pipe.
  - Let Render Lyric Captions accept `{}` as automatic alignment for edited lyrics. This marker passes through empty-string fallback switches while muted manual inputs still select the original timing; populated timing JSON retains strict validation.
  - Add Play and Stop controls to Transcribe Audio. Play opens the transcript and runs only its upstream branch; Stop pauses normal queues after changed results, with cached continuation when queued again unchanged. The collapsed bar keeps Play beside its summary. Existing workflows keep Stop disabled.
  - Add optional image-change warmup to WAN LipSync Timeline Planner. Plan Step supplies trim_image for overlap plus warmup and audio_start for conditioning; its crop output applies to both IMAGE batches and disk timelines. Hidden lead-in frames use preceding guide audio without shifting visible transitions or the soundtrack. Warmup stays within the fixed render window and defaults to disabled.
- **Fix**
  - Filter the recurring “Satsang with Mooji” attribution artifact from automatic transcripts and lyric-recognition windows, including its word timestamps. Preserve surrounding lyrics and explicit manual text/timing; report filtered occurrences and invalidate older transcription caches.
  - Recover short unmatched lyric sections, including openings and endings, with confined recognition retries on vocals and the original audio. Align recovered words using their matching audio source while preserving thresholds and neighboring timing; invalidate older alignment cache results.
  - Preserve panel node widths when expanding or collapsing option bars and sections, including Add Filename Prefix, Smart Prompt, sampler and media panels. Heights continue adapting to controls, while resizable text and preview panels retain their existing height behavior.
- **Docs**
  - Explain lyric and timing correction priority, optional Qwen dependencies and model setup, transcript/preview controls, and Wan warmup and disk-timeline connections.
- **Changed files**
  - core/transcription_cleanup.py
  - core/lyric_qwen.py
  - core/lyric_caption_configuration.py
  - requirements-qwen.txt
  - core/audio_transcription.py
  - core/lyric_cache.py
  - core/lyric_reference.py
  - core/lyric_caption_pipe.py
  - py/RvPipe_IO_LyricCaptions.py
  - py/RvVideo_RenderLyricCaptionsPipe.py
  - js/eclipse-caption-state.js
  - js/eclipse-caption-form.js
  - js/eclipse-caption-panel.js
  - js/eclipse-panel-seed-queue.js
  - Readme/README.md
  - core/lyric_alignment.py
  - core/lyric_captions.py
  - py/RvVideo_RenderLyricCaptions.py
  - Readme/Lyric_Captions.md
  - core/wan_motion_context.py
  - py/RvVideo_WanLipSyncConditioning.py
  - Readme/Frame_Timeline.md
  - core/operation_panel.py
  - core/operation_panel_layouts.py
  - js/eclipse-operation-state.js
  - js/eclipse-operation-form.js
  - js/eclipse-panel-run.js
  - py/RvAudio_TranscribeAudio.py
  - py/RvVideo_WanLipSyncPlanStep.py
  - py/RvVideo_WanLipSyncTimelinePlanner.py
  - js/eclipse-configuration-panel.js
  - js/eclipse-sampler.js
  - js/eclipse-save-images-panel.js
  - js/eclipse-save-video-panel.js
  - js/eclipse-smart-prompt.js
  - js/eclipse-video-panel.js
  - Readme/Load_Video.md
  - pyproject.toml

## 2026-10-21

### Version: 1.0.9

- **Fix**
  - Preserve the resized Detailer SEGS node height on workflow reload, before its first render and with preview disabled.
- **Changed files**
  - js/eclipse-sampler.js
  - pyproject.toml

## 2026-10-21

### Version: 1.0.8

- **Feat (New)**
  - Add PIPE-only Eclipse KSampler Advanced with standard/two-stage modes, independent step ranges and noise controls, optional between-stage latent upscale, a shared base seed and Stage 2 offset, and final-only decoding. Defaults match the configured Nova sampler in the Moody Moss workflow, including 2× bicubic upscale.
  - Add IO KSampler to control both sampling stages, seeds, noise toggles, latent upscale, preview and decode through a PIPE, using the standard sampler fields for Stage 1 and separate Stage 2 fields, with local fallback for missing values and preservation of other metadata.
- **Feat**
  - Support Image Selector seed locking for the new advanced sampler.
  - Add adjacent model_1 and model_2 connections to IO KSampler for high/low-noise model pairs, with latent-format checks, independent model patches and preview-decoder replacement at the handoff. Stage 2 automatically reuses model_1 when model_2 is absent from the PIPE.
  - Add optional Qwen schedule, DiT skip guidance and Detail Daemon sections with value tooltips and local-only controls independent of PIPE overrides. Recalculate Qwen sigmas per stage resolution, isolate model patches, and include the Detail Daemon curve and sampler wrapper.
  - Give both Eclipse samplers a shared live/final preview that resizes with the node and supports batch thumbnail selection, click-to-next navigation and returning to the grid in both renderers.
- **Fix**
  - Restore local preview visibility immediately when Use pipe settings changes, and preserve wrapped sampler inpainting options in Detail Daemon.
  - Use 0.1 increments for general float controls, retaining finer precision where fractional defaults or bounds require it, including Qwen schedule and Detail Daemon controls, sampler noise, MiniMax timing, audio alignment and resolution controls so valid values are not marked invalid.
  - Preserve structured LoRA and audio payloads in Concat Pipe Multi while retaining arbitrary PIPE fields and advanced sampler controls. Reject malformed tuple inputs and unsupported merge options. Document loader-to-sampler PIPE extraction and overwrite ordering for resolved generation data.
  - Bound sampler live-preview resolution before TAESD decoding and reuse one decoder across advanced sampling stages. Preview-only out-of-memory errors disable live frames while sampling and final decoding continue.
- **Changed files**
  - py/RvConversion_ConcatMulti.py
  - Readme/Utility_Nodes.md
  - core/advanced_sampler.py
  - core/sampler_extras.py
  - core/detail_daemon.py
  - licenses/detail-daemon-MIT.txt
  - core/sampler_configuration.py
  - core/sampler_execution.py
  - core/sampler_preview.py
  - py/RvSampler_KSamplerAdvanced.py
  - py/RvPipe_IO_KSampler.py
  - js/eclipse-sampler-state.js
  - js/eclipse-sampler-form.js
  - js/eclipse-sampler.js
  - js/eclipse-sampler-queue.js
  - js/eclipse-image-selector.js
  - js/eclipse-detailer-preview.js
  - js/eclipse-panel.css
  - Readme/Sampler.md
  - Readme/Advanced_Sampler.md
  - Readme/README.md
  - pyproject.toml

  - py/RvVideo_RenderLyricCaptions.py
  - py/RvRouter_Float_Passer.py
  - py/RvAudio_LoopCalc.py
  - py/RvTools_ResolutionScale.py
  - py/RvAudio_LoopAlignSilence.py
  - py/RvVideo_WanLipSyncTimelinePlanner.py
  - py/RvVideo_TrimToShortest.py
  - py/RvLogic_Float.py
  - core/save_video_configuration.py
  - core/video_panel_configuration.py
  - core/lyric_caption_configuration.py
  - core/minimax_h3_configuration.py
  - core/resolution_sizing.py
  - core/audio_loader_configuration.py
  - core/smart_folder.py
  - js/eclipse-load-audio-panel.js
  - js/eclipse-video-panel.js

## 2026-10-20

### Version: 1.0.7

- **Fix**
  - Refresh Save Images and shared image previews when filenames are reused, preventing stale browser-cached pictures while retaining cached navigation within each result.
  - Ignore late preview dimension responses from previous results after a newer batch arrives or the preview is cleared.
- **Changed files**
  - js/eclipse-dom-preview.js
  - pyproject.toml

## 2026-10-20

### Version: 1.0.6

- **Fix**
  - Image Selector confirmation locks both Dual Seed values to the displayed execution, preserving full 64-bit precision and saved workflow selections.
- **Changed files**
  - js/eclipse-image-selector.js
  - pyproject.toml

## 2026-10-20

### Version: 1.0.5

- **Feat (New)**
  - Add Dual Seed_v2 with independent Image and Prompt controls and outputs, one shared 64-bit toggle, and reusable paired results.
- **Feat**
  - Keep up to 50 recent results in Seed and Dual Seed; histories persist with workflows.
- **Changed files**
  - core/dual_seed_configuration.py
  - py/RvLogic_DualSeed.py
  - js/eclipse-dual-seed-panel.js
  - js/eclipse-dual-seed-queue.js
  - js/eclipse-dual-seed-state.js
  - js/eclipse-panel-seed-controls.js
  - js/eclipse-seed-panel.js
  - js/eclipse-seed-state.js
  - Readme/Seed.md
  - Readme/README.md
  - pyproject.toml

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
