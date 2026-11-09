# Reference scene and motion analysis

The scene-analysis nodes measure a reference video's scene boundaries and describe the performance between them. Eclipse handles detection, sampling, collection and H3 export; [SmartLLM Nova](https://github.com/r-vage/ComfyUI_SmartLLM_Nova) supplies the image descriptions. The connections below can be added to your own graph.

Use Eclipse **Loop Start / Loop End** to process one sampled window per iteration:

`Load Video → Scene Detector → Scene Cut Limit (optional) → Scene Analysis Plan → Loop Start [Scene Frame Sampler → Smart LM Prompt Pipe → Smart LM Loader → Scene Description Collector] → Loop End → Save Scene Analysis → Scene Analysis to H3`

Connect the sampler's `frame_source` directly to Smart LM Loader's `frame_source`, and its `context` to Smart LM Prompt Pipe's `user_prompt`. Connect the pipe's `settings` to the loader's `pipe_opt`, then the loader's `text` to Scene Description Collector.

## Optional live/manual routing

To keep editable manual values alongside live analysis, put the analysis nodes in an optional group and select one complete source of part inputs:

| Source | Part inputs |
| --- | --- |
| Manual | Editable cut times, first part and next parts |
| Live | Reference-video analysis loop |
| Saved analysis | Load Scene Analysis → Scene Analysis to H3 |

Use [Mode Bridge Set/Get and Mode Relay](Set_Get_Bridge.md) to control the live group's enabled state, or mute the group directly. Keep the reference image, audio selection and trim as the rendering inputs; choose matching source audio and trim when transferring timings.

Keep the global performance prompt and its Set node in a separate enabled group so muting either part-input group does not remove it. The manual group should contain only editable cut times, the first-part description and next-part descriptions. Selecting live analysis should route its outputs without overwriting this manual text.

Enter the first part's framing and movement separately. For subsequent parts, use one description per non-empty line in String Multiline and connect its `string_list` to the planner's `technical_cut_instruction`. Timings are comma-separated seconds from the selected audio's start. Clear the times for no manual cuts; clear the part descriptions as well to use only the global performance prompt.

Pack each source's timings, next-part prompts and first-part prompt into one **Pipe 12CH Any**. Use Set/Get between groups, **Get All Active** to resolve enabled sources, and **Any Multi-Switch Lazy** to select one whole pipe. This keeps empty fields attached to their selected source: a reference with no cuts must not inherit old manual cuts. After selection, unpack the values and keep subsequent prompts as a list; if carried as multiline text, split it back into one item per part.

For saved results, connect **Load Scene Analysis** directly to **Scene Analysis to H3**. This reuses the measured timings and descriptions without running detection or the LM again.

## Detection and image detail

Scene Detector scans **every decoded source frame**, on CPU, at a default longest side of **128 px**. It uses PySceneDetect AdaptiveDetector with threshold 2.5, window width 4, minimum content 15 and minimum scene length 1 frame. Install `scenedetect>=0.7.2,<0.8` in the ComfyUI environment. The detector preserves presentation timing from native VIDEO, including trims and variable frame durations. Cuts are measured boundaries, not language-model guesses. Sensitivity is adjustable; fades, very similar shots and flashes can need different settings.

Optional **Scene Cut Limit → max_cuts_per_second** filters the detected plan before sampling. Zero passes it through unchanged; 1 keeps cuts at least one second apart, 2 requires half a second, and 0.5 requires two seconds. It keeps the earliest candidate meeting the interval measured from the previous retained boundary, including the source start. It never moves a cut. The final scene may be shorter than that interval, so the full source duration remains covered.

Excluded cuts merge adjacent scenes. The plan records their source frame positions, and any analysis window crossing one tells the LM that a sudden pose change across that edit does not prove physical movement. A stricter limit can omit brief events from a uniform sample budget; review the merged descriptions. Changing this node reuses cached detection but reruns sampling and descriptions for the new scene ranges. Use **0 = unlimited** to preserve every detected boundary.

Smart LM uses a separate **Longest side** in its **Image handling** section below Model. Start with **512 px** for faces and gestures, then review the descriptions. Zero keeps automatic model sizing; a positive value is bounded by the loader/model limits. Original IMAGE passthrough remains unchanged. Dynamic patch alignment can round dimensions down, and incompatible fixed/minimum processor sizes produce a clear error where their requirements are available. Remote backends still control their own final preprocessing.

**Image handling** opens and collapses independently of Model and can be pinned open. Its settings are independent of task, Direct Chat and system overrides. **Together: On** describes the ordered frames in one request; **Off** describes each supplied image separately. Use On for motion across a scene window. Together uses the supplied selection, without the legacy last-N `frame_count` truncation. Older loader configurations retain a compatibility mode. H3 first/last reference tasks require Together when configuring a new loader with two reference images.

**Every Nth frame** in Smart LM applies to Together and always retains the first and last supplied image. It operates on the supplied selection: N=2 on eight uniformly selected frames sends positions 0, 2, 4, 6 and 7, not every second original video frame. Use N=1 to retain all selected frames. Brief gestures and expressions can still fall between samples or be missed by the model.

## Sampling and bounded memory

Scene Analysis Plan supports a uniform sample budget per scene or **every_nth** original-frame selection. The stride resets at each scene. Scene ranges are `[start, end_exclusive)`; their final sample is `end_exclusive - 1`, never the next scene's opening frame. One-frame scenes are deduplicated. Select original every-Nth sampling here for regular temporal coverage, and normally leave the LM stride at 1 to avoid sampling twice.

Selections larger than `max_frames` become overlapping windows. The defaults are eight frames per request and two shared samples between windows. Windows retain their scene ID and never create additional cuts. Use `window_count` as the loop's total and connect its zero-based index to both Scene Frame Sampler and Scene Description Collector. Initialize the loop state with `empty_descriptions`, carry the collector's updated descriptions into the next iteration, and send the final state plus the same `jobs` to Save Scene Analysis.

Connect Start's `loop` to End's `loop`, the collector to End's `value`, and Start's
`previous` to the collector's accumulated descriptions. Select **block downstream**
on End so an intentionally stopped analysis does not reach the complete-analysis
saver. Completed unchanged windows can reuse ComfyUI's cache. This generic loop
does not persist partial analysis progress across server restarts; video render
resume instead restores the completed, resolved analysis prompts saved with the
run. See [Eclipse loops](Loops.md).

For up to **16 images together**, set **samples_per_scene = 16** and **max_frames = 16**, then use Smart LM **Together** with **Every Nth = 1**. Increasing only `max_frames` does not increase the uniform sample budget. Short scenes can provide fewer images. All scene-analysis nodes have input/output tooltips with practical settings and connection guidance.

The detector streams frames; the planner makes one additional streaming pass to cache only selected frames as uint8 data on disk. Scene Frame Sampler passes `SMARTLLM_FRAME_SOURCE` references, not IMAGE tensors. Smart LM materializes only the current request, resizes before batching, and returns an empty IMAGE list for this lazy input. Ordinary IMAGE input still passes through normally. Loop state contains descriptions and metadata. Cache files remain valid while graph outputs refer to them and are deleted when those owners are released. A file-backed VIDEO is required for bounded source decoding; a VIDEO built from an already loaded image batch still owns that batch.

## Descriptions and recovery

The optional **Video Run Storage → storage** input on Scene Analysis Plan shares
the generation loop's Disk/RAM control. Disk off keeps selected uint8 images in
CPU RAM, increasing memory use without writing image-cache files. Detection still
streams the source, and Smart LM still processes one window at a time. Disk on
uses temporary analysis images regardless of Keep files; that option retains
generated video parts. Diagnostic response JSON is written in either mode.

Select **Scene Motion Analysis** for image-to-video. Its prompt focuses on transferable shot geometry, camera movement, existing body positions, body/hand motion, gaze and expressions. The separate target reference supplies appearance and setting. It requests a `performance_prompt` plus supporting observations, using neutral subject/body terms and usually 20–50 words in one to three sentences. The requested schema needs no `appearance` field. Every sentence should provide useful visual direction; measured timing and audio handling remain in the planner.

Select **Scene Description (T2V)** for a complete visual description. Its paragraph includes relevant visible appearance, clothing, setting, lighting, framing and movement. The additional `appearance` field is optional supporting metadata: omitting it does not stop collection or request another model call. If it is blank or uses a structured format, it is retained with a review warning. Generation uses the unchanged `performance_prompt` paragraph. The task remains grounded in the supplied images and does not infer sound or unseen events. Both tasks write their paragraph in the same call as the observations; neither needs a separate rewriting pass. The existing single correction attempt remains available for invalid output. Task selection is recorded as `description_mode` by Smart LM, independently of what the model returns.

For ordinary image tasks such as Detailed/Ultra Detailed Description or MiniMax H3,
enable **Scene JSON** in Smart LM Loader's Mode bar and **Together: On** in Image
handling. The loader builds a `scene_caption` version-1 JSON envelope in code from
the task's normal answer, without asking the model for JSON or adding an inference
call. The collector stores its scene paragraph and full original response, without
inventing pose/action audit fields. H3 uses its visual-description field for the
paragraph and retains the full response for review. Choose **include source
appearance** in Scene Analysis to H3: captions keep the selected task's wording.
Turning Scene JSON off preserves direct text output for existing workflows.

Connect sampler `context` to the Prompt Pipe's **user_prompt**, not its system_prompt. It supplies scene/window IDs and measured frame information without prescribing an output format. Keep the same task throughout the loop. A custom system prompt intentionally replaces the selected task instructions, while grouping and sizing remain in effect; enable Scene JSON to package its ordinary text for the collector.

Starting and ending poses are snapshots of positions already present. A scene can start partway through a gesture: hands already beside the head do not imply raising them there. Actions describe only the visible continuation between samples, including finger or wrist movement while the arms stay in place. The performance paragraph describes an existing pose and continuing motion naturally, without inventing preparation, a complete gesture cycle or a return to rest.

The collector verifies IDs, fields, required paragraph and window order. Usable text that includes unwanted appearance, excessive detail or questionable pose wording is kept unchanged with `review_warnings`; it does not stop the loop or trigger another LM call. Save Scene Analysis and Scene Analysis to H3 include these warnings in their reports. You can copy the resulting part prompts into the manual inputs and edit them. Older cached responses carrying a content `contract_error` are also accepted when their actual data is valid.

If the model returns `actions`, `gaze_expression` or `uncertainties` as a text string, Smart LM and the collector accept it as one list item without changing the wording or splitting at commas. A blank string becomes an empty list. This formatting difference needs no correction call and does not stop collection, including for cached responses. The collector keeps its original received response in the recovery file.

For the dedicated structured scene tasks, incomplete JSON, missing required text, non-text action/expression/uncertainty values, mismatched IDs or incomplete coverage still stop with a scene/window-specific error and a recovery JSON path. These structural failures use the existing single correction attempt in Smart LM; no scene is silently discarded. Application-built captions instead validate their envelope, text, IDs and available request evidence; formatting inside the model's text cannot break the JSON. Saved **version-2** analyses support both observation types and contain measured boundaries, window selections and generation paragraphs. New motion results need no appearance field; full descriptions can include it as supporting metadata. Older unmarked results still require text appearance metadata for their legacy export processing. Version-1 exports and observations without `performance_prompt` require a new analysis. Smart LM adds actual request positions and dimensions as `input_evidence`; these are mapped back to source frame IDs/timestamps, so its stride is auditable.

Both tasks summarize distinct movements instead of producing one event per sample or listing every speech-like mouth shape. They contain no example pose for the model to copy. Smart LM filters exactly black frames after stride and resizing, before inference. Starting/ending poses refer to the first/last image actually sent. Dark images with any nonzero pixel are kept, and the ordinary IMAGE passthrough is unchanged. Other tasks retain their image behavior.

`input_evidence.positions` lists sent positions and `omitted_black_positions` lists filtered positions, both zero-based within the sampler's original selection. The collector maps both to source frame IDs and timestamps. If every selected image is black, inference is skipped and the node emits an explicit observation with `image_count: 0` and `skipped_reason: all_black`. The corresponding H3 part remains `Black screen.`. No measured scene boundary or audio timing moves, and no part disappears from the timeline. Model loading may still occur before the selection is prepared.

**Save Scene Analysis → filename_prefix** is an editable label, not the selected video name. Changing the Load Video file does not update that label. Check the selected video and trim, plus the saved source dimensions/duration, when comparing runs with similar filenames.

## H3 connections

For N scenes, **Scene Analysis to H3** returns N−1 measured cut times, N−1 `next_part_prompts`, a global `main_prompt`, and a separate `first_part_prompt`. The next-part descriptions use the planner's existing `technical_cut_instruction` socket; each description is the prompt for the part beginning at that cut.

Match the **appearance_mode** dropdown to the analysis task: **Exclude source appearance** for Scene Motion Analysis, or **Include source appearance** for Scene Description (T2V). New task paragraphs pass through unchanged, without appearance removal or reconstruction from audit fields. The dropdown selects the intended policy; it cannot guarantee that the model followed it. Review warnings and manually edit unwanted details before generation. A mismatched selection stops with instructions to choose the matching mode or rerun the other task. Motion analysis does not request a complete appearance description to recover later. Adjust the global performance prompt's reference-image instructions when preparing T2V prompts, and configure the downstream generator for text-to-video separately.

Older version-2 results without `description_mode` retain their existing export behavior: exclude filters recognized source appearance, and include prepends stored appearance to the cleaned motion paragraph without new inference. Their raw observations remain available for review. These compatibility rules do not rewrite new task-specific paragraphs. Review model responses: task instructions reduce unwanted detail but cannot guarantee compliance or correct motion interpretation.

The global prompt describes performance throughout the video, such as lip-syncing to the supplied audio and preserving the selected image's identity. Individual part paragraphs describe meaningful framing, poses, expressions and movement. Ordinary mouth-opening cycles remain audit observations; intentional mouth gestures can remain in the performance paragraph. Paragraph instructions exclude clip durations, readiness commands and audio-priority claims.

**MiniMax H3 Segmented Conditioning** combines the global prompt with the active part only. The first-part pose applies until the first planned cut, including any capacity splits inside that part. Later parts receive their own descriptions; the opening pose is absent from their encoded text. With no part descriptions connected, the global prompt works alone. Keep both `segment_plan` and `task_index` connected for part selection.

Measured cut positions, crop ranges and audio slices remain in the planner. The conditioner sends one continuous-shot description for each part; the final cuts are made when the retained parts are joined. It does not insert another timed shot change inside the hidden warmup. Source-image guides, hidden warmups, audio conditioning and the final source-audio mux are unchanged.

The default FL2VA setup retains the exact reference image at global frame 0. If its hands are in a different position from the observed opening pose, text alone cannot make both positions true in that frame. The model may visibly reposition the hands during a short opening part. Use a matching initial image when exact frame 0 is required; an opening warmup would instead need a generated first visible frame. Later parts already have hidden warmups. Prompt wording does not guarantee identity, gesture accuracy, lip-sync or hand anatomy.

The exporter uses ready-written performance paragraphs. Windows within a scene are joined in order, suppressing only identical neighboring paragraphs from shared samples; later recurrences remain. New task-specific paragraphs and explicit edits keep their wording. Older unmarked observations retain bounded appearance and routine mouth-sentence cleanup. All-black selections receive a `Black screen.` paragraph without inference, keeping their part present and measured timing unchanged.

Prompts are single paragraphs so H3's line-based prompt selector keeps each description intact. Save Scene Analysis writes version-2 files that Load Scene Analysis can read directly. Manual prompt inputs can be wired independently of the analysis JSON. Cleanup applies only to older unmarked results and cannot recover an omitted gesture; new task paragraphs retain their wording and review warnings. Review the paragraphs and sampled-frame evidence before rendering.

Use **[Prompt Review](Prompt_Review.md)** between Scene Analysis to H3 and the
planner to review generated text directly. Connect `first_part_prompt` to its
`first_prompt` input and `next_part_prompts` to `prompts`; route its corresponding
outputs onward. Pause defaults to off and passes the original text through.
Enable Pause before queueing to edit the opening and later prompts together,
then press Continue to use the edits in that same run. Keep one paragraph per
scene when joining the list for a line-based H3 planner.

| Adapter output | Destination |
| --- | --- |
| `manual_transition_times` | MiniMax H3 Audio Timeline Planner → `manual_transition_times` |
| `next_part_prompts` | MiniMax H3 Audio Timeline Planner → `technical_cut_instruction` |
| `main_prompt` | Both base and extension MiniMax H3 Segmented Conditioning → `prompts` |
| `first_part_prompt` | Both base and extension MiniMax H3 Segmented Conditioning → `first_part_prompt` |
| `report` | Show Any or another text preview for counts and review warnings |

Keep one appearance reference image, use the same source audio/trim and choose original-image resets at manual cuts. The source video supplies performance, not replacement identity. The adapter checks H3's 24 FPS quantization and rejects cuts that collapse to the same frame. Timing is not automatically stretched to unrelated audio. Load Scene Analysis validates a saved file so later rendering does not rerun detection or the LM. Review descriptions and uncertainties before an expensive render.

## Choosing detail and memory settings

At 128 px, PySceneDetect 0.7.2 reproduced the reviewed boundaries of two reference clips with 29 and 14 cuts. This is a starting point, not a universal detection limit: inspect the measured boundaries on each new source and adjust resolution or sensitivity when needed.

Use a higher Smart LM resolution or denser sampling when details are missing, while keeping each window within the model's memory budget. A larger image alone does not guarantee accurate finger motion or expressions; a reviewed opening gesture remained incomplete at both 512 and 1024 px. The model can also misread partially obscured poses. Compare the descriptions with the source before transferring them to generation.

Thinking is optional on supported models. Its tokens share the output allowance with the answer; increase **Max tokens** if the model runs out of room for complete scene JSON. Usable descriptions with content warnings remain available for manual editing.
