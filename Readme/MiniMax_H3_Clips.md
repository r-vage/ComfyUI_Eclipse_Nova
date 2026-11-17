# MiniMax H3 native clips

## Unified workflow prompt flow

`MMH3_Unified_TFL2VA.json` uses **H3 Prompt Plan_v2** to resolve timing, image
assignments and complete scene instructions before optional LLM description.
The original Clip Planner and Clip Planner_v2 remain available.

| Inputs without reference video | Logical clips | Images |
| --- | --- | --- |
| Two or more images | One per enabled image | First prompt for image 1, next prompts for subsequent images |
| One image | First prompt plus each nonblank next-prompt entry | Reuse the image for every clip |
| No images | Same first/next prompt list | Text-only generation |

A blank first prompt still reserves the opening clip. Missing later instructions
use global direction alone; extra prompts for multiple images produce an error.
Without a prompt list or reference media, the workflow creates one text-only clip.
Technical render splits retain the logical clip's prompt and image.

**Global instructions** applies to every clip. **First clip** supplies the
opening instruction, and each nonblank **Next clips** line supplies the next
instruction. With **LLM descriptions** enabled, H3 Prompt Inputs_v2 pairs these
complete instructions with their assigned images, or text alone, and sends them
through Smart LM Prompt Pipe to the selected LLM task. Each result replaces its
input instructions; the raw first/next/global text is not appended again. Select
a task that accepts text for text-only generation. The MiniMax H3 Scene task
supports both image and text inputs. With LLM descriptions off, the same planned
instructions go directly to generation.

The connected prompt list overrides Smart LM Loader's local Prompt field unless
its **Merge user prompt** option is enabled. Use Global instructions for shared
direction, or enable Merge to add the loader's local guidance to every request.

**Part source → Final generation prompts** displays the resolved list, after
LLM description when enabled. Queue the workflow to populate it. Use the prompt
selector to inspect each logical clip; technical splits share its text. Pause is
off by default. Reviewed edits reach H3 Reviewed Plan_v2 before generation,
preserving timing, images and soundtrack. No separate prompt file is written.

## Timing and video analysis

Without video, **Duration per clip/image** is the duration of each clip when cut
times are blank. Explicit cuts specify the N−1 boundaries for N clips within the
same total duration of N × Duration. For example, three clips at four seconds
with cuts `3, 8` produce lengths of three, five and four seconds. Invalid cut
counts or cuts outside the total duration produce an error.

With a reference-video playlist, duration 0 preserves each loaded clip's trimmed
timing. A positive duration overrides each source clip and scales its scene cuts.
Images cycle by source clip, keeping the same reference through every scene and
technical split in that clip. Excess images are unused. Without explicit cuts,
a prompt list longer than the video playlist is distributed across the source
timeline, retaining source boundaries. Generation uses the 24 FPS frame grid.

**Live analysis** supplies video cuts and scene descriptions in place of the
manual cut/first/next fields. Global instructions still applies. Select the
video LLM task and Scene Analysis to H3 appearance mode manually: Scene Motion
Analysis with exclude source appearance when images supply appearance, or Scene
Description (T2V) with include source appearance for full textual descriptions.
Optional LLM descriptions then refines each planned scene using its assigned
image, or text alone. With Live analysis off, manual fields are used.

Connect the same Load Video output to planning and scene analysis. Place Scene
Source Boundaries_v2 after Scene Cut Limit and before Scene Analysis Plan to
retain playlist boundaries even when adjacent clips look alike. Keep playlist
transitions set to Cut. VIDEO producers without Eclipse playlist provenance are
treated as a single source clip.

## Hidden warmup for camera and pose

H3 Prompt Plan_v2 and Clip Planner_v2 provide **opening_warmup_seconds** and
**warmup_seconds**. Both default to zero for existing graphs. The updated TF2VA
workflow sets each to one second; set either to zero to disable that lead-in.

The opening setting applies to the first render. The later setting applies to
every subsequent independent render, including capacity splits of a long scene.
Each render uses its scene's complete reviewed prompt throughout. Its assigned
image anchors the hidden opening; the visible clip begins after the discarded
lead-in, giving the prompt time to establish its requested camera and pose.
This also works with multiple images and text-only clips. Settling time varies
with the model and prompt; this does not guarantee a completed pose change.

Use **MiniMax H3 Clip Conditioning_v2**, then connect both **crop_start** and
**keep_frames** to **Append Video Clip_v2**. The latter discards the same time
range from decoded video and generated audio. Existing conditioning and append
nodes remain available for graphs without warmup.

Visible scene durations, cut positions and selected soundtrack timing remain
unchanged. Hidden frames consume the Max clip frames budget and may add render
parts. For example, five visible seconds with one second of warmup requires
144 frames before H3 grid padding, then retains 120 frames after discarding 24.
Warmup crops the initial transition; renders still independently use their
assigned image and do not acquire motion continuation from a previous clip.

## Soundtrack and saved runs

Audio priority is a dedicated recording, then unmuted source-video audio, then
H3-generated sound. Use Load Audio's **Start** and **Duration** to select a
dedicated excerpt; audio Duration 0 means the remainder of the recording.
The selected excerpt loops when short and is trimmed when long. Looping never
uses material outside that excerpt. Audio is attached during assembly and is
not passed as a lip-sync or native audio guide. Muted/missing source tracks permit
generated sound; an intentional silent recording remains a selected recording.

Persistent runs save resolved clip timing, source/image assignments, prompts,
soundtrack, audio-excerpt settings and per-render warmup crops. Resume restores
them without fresh analysis; part prompt edits preserve those crops. Existing
runs without warmup metadata retain zero crop. Start a New run to apply changed
warmup settings; Resume and Update keep the saved render layout.

**Clip Planner_v2** retains its earlier contract: independent image descriptions
are appended with global and scene directions, with one source clip per image
when no video is connected. Use H3 Prompt Plan_v2 and H3 Reviewed Plan_v2 for the
unified workflow's instructions → optional LLM → final prompt flow.

## Original Clip Planner

**MiniMax H3 Clip Planner** and **MiniMax H3 Clip Conditioning** support native
text-to-video-and-audio, visual-reference and first/last-image generation. They
call ComfyUI's `MiniMaxH3ImageToVideo` or `MiniMaxH3ReferenceToVideo` and, when a
soundtrack is selected, `MiniMaxH3AddGuide`.
Use a MiniMax H3 model, its Qwen text encoder, video VAE and audio VAE. These nodes
do not use the separate lip-sync audio encoder.

## Audio and duration

| Available input | Soundtrack | Duration |
| --- | --- | --- |
| Loaded AUDIO | Loaded recording | Loaded audio length |
| Reference VIDEO with usable source audio | Reference recording | Reference video timing |
| Silent or fully muted reference VIDEO | H3-generated audio | Reference video timing |
| Neither | H3-generated audio | Planner's Duration |

Loaded audio takes priority over reference audio. A reference with an actual
silent audio track still counts as a recording; the planner does not measure
loudness to make this choice. Load Video retains whether its selected sources
have unmuted audio, so its synthesized silence for missing tracks does not block
the generated-audio fallback. For mixed playlists, silent intervals remain part
of the reference recording.

Use the same trimmed VIDEO for scene analysis and the planner. A separately loaded
recording must be aligned to that reference yourself. Cuts are measured from the
selected source's start, at H3's **24 FPS**.

## Plan and loop

Connect global direction to **prompt**, opening direction to **first_prompt**,
comma-separated seconds to **cut_times**, and one subsequent part paragraph per
line to **next_prompts**. The global direction applies throughout. Missing part
text uses global direction alone. Cuts at or beyond the chosen duration are
ignored and reported.

With **blank cut times**, the first prompt and each nonempty next-prompt line
define scenes of equal duration (to within one frame). For example, 40 seconds
with four scene prompts produces four 10-second scenes. A single scene instead
fills the duration and splits only at the render limit. Supplied cut times always
take priority, including times measured by reference-video analysis.

**Max clip frames** limits each model invocation to a supported length from 124
to 362. A longer part splits into independent clips using the same part prompt.
Short parts still render at least 124 frames, then discard padding. This preserves
the cut clock but does not reduce sampling cost in proportion to a very short
part. Capacity splits do not provide latent or motion continuation.

Wire the loop as follows:

1. Planner **plan** → **Video Loop Start**, along with canvas size, references
   and **Video Run Storage**. Start's resolved **plan**, **index**, **images**,
   **width**, **height** and **reference_mode** → Clip Conditioning.
2. Clip Conditioning **positive** → BasicGuider; **latent** → SamplerCustomAdvanced.
3. Seed → **Video Part Seed → RandomNoise**, with the loop index connected to
   Video Part Seed. Keep Clip Conditioning's seed fixed and leave its seed output
   unused to isolate sampling changes from encoding. Its original seed output
   remains supported for existing workflows.
4. Decode the sampled joint latent with both **VAE Decode** and **VAE Decode Audio**.
5. Both decoded outputs → **Append Video Clip**, with **keep_frames** from Clip
   Conditioning and **previous** from the loop's carried VIDEO value.
6. Video Loop Start **audio** → Append Video Clip **soundtrack**, and Start's
   **storage** → Append Video Clip **storage**. The audio is the full
   recording from time zero; the conditioner handles per-clip guide slices.
7. **Append Video Clip → Preview Video → Loop End value**, with Start's **loop**
   connected to End's **loop**. End returns the final accumulated VIDEO.
   Leave Save Video's **Audio input** mode disabled: the VIDEO already contains
   the selected recording or the generated audio.

By default, Append Video Clip stores each retained clip on temporary disk with RGB8 video and PCM audio.
Loop state references those files rather than accumulating decoded image tensors.
The final save performs the delivery encode. Cached outputs keep temporary files
alive; interruption removes a partially written clip.

Connect **Video Run Storage** to choose temporary disk, persistent output or CPU
RAM. Persistent mode saves ordered clips and a `run.json` for **Load Video Run**,
including a selected master soundtrack when supplied. RAM mode shares decoded
parts across loop iterations without clip-cache files. Preview Video returns the
original accumulated VIDEO; its viewing copy does not replace the loop state.
See [frame storage and saved runs](Frame_Timeline.md#ram-disk-and-saved-runs) for
the controls, loading and lifetime rules. These modes also support lip-sync
frame timelines through Decode and Append Timeline.

For a stopped run or a replacement from part N onward, select **Resume saved run**
in Video Run Storage. **Video Loop Start** restores the saved inputs and supplies
the absolute index to conditioning and Video Part Seed. Limit **parts_per_queue**
or use **Stop after current part** to review the accumulated result. Change the
render seed before the next queue to vary replacement clips while retaining the
earlier saved parts. See
[resume controls](Frame_Timeline.md#resume-or-replace-the-remaining-parts).

To regenerate one saved clip while keeping the ending, choose **Update selected
run** and set **Restart part** to its one-based number. The loop renders
one clip, reuses every other saved clip and keeps the same folder selected.
Retained clips keep their generated audio;
an external master soundtrack stays unchanged.

Use **Update selected run** with **Disk + Keep in output** to keep the same folder
selected across corrections. Each successful replacement backs up the previous
version. Load Video Run can preview a selected backup or restore it, including its
saved prompts and generated clip audio. Restore preserves the displaced version
as another backup. See [update and restore](Loops.md#update-the-same-run-and-restore-a-backup).

## Reference images

Connect **Load Image Timeline → images** to Clip Conditioning. Its shared canvas
and each slot's crop settings replace separate loader/resize pairs. Use the same
width and height for that loader and generation. Disable the image source group
for generation without references; an active empty Load Image Timeline requires
at least one enabled image.

| Reference mode | Image selection |
| --- | --- |
| first_and_last | First and last enabled images for every clip; one image anchors only the start |
| first_only | First enabled image anchors each clip's start |
| last_only | Last enabled image anchors each clip's end |
| first_per_scene | Image 1 starts scene 1, image 2 starts scene 2, etc.; reuse the final image if scenes outnumber images |
| first_middle_first | FMF: exactly two images, used as image 1 → image 2 → image 1; later scenes keep image 1 |
| adjacent_pairs | Images 1→2, 2→3, etc. per part; after the images are exhausted, the final image anchors the start |
| reference_images | Up to 9 enabled images supply native visual references without fixing the first or last frame |
| text_only | Ignore connected images and generate from the prompt |

In **reference_images**, prompt tags such as `<Picture 1>` identify images in
their enabled timeline order. When the prompt contains no picture tags, the node
adds a short direction to use the supplied images as visual references. With no
images, it uses text-to-video-and-audio. **text_only** ignores images even when
the loader is enabled; muting the loader also avoids loading them.

Scenes normally come from cut times or the untimed prompt list. Image slots do not create
scene boundaries themselves; **first_middle_first** adds missing sections as described below.
Capacity splits retain the same scene number, so **first_per_scene**, **first_middle_first**
and **adjacent_pairs** keep the scene's image assignment
throughout those renders. Clips remain independent generations; reusing an image
does not guarantee continuous motion or generated sound across their joins.

### FMF: first, middle, first

For a brief alternate appearance followed by a return, enable exactly two image
slots and choose **first_middle_first** in **Video Loop Start → reference_mode**.
The loop applies FMF to the incoming native H3 plan before saving its inputs.
In a standalone planner/conditioner chain, select the mode in **both Clip Planner
and Clip Conditioning**, and use the planner's updated clip count.

- With two or more detected/manual cuts, their positions are preserved. Image 1
  starts scene 1, image 2 starts scene 2, then image 1 starts every remaining scene.
- With no supplied cuts, the duration is divided into three equal sections on
  H3's 24 FPS clock. Up to three scene descriptions are used; additional untimed
  descriptions are reported as unused.
- With one supplied cut, it stays fixed and the remaining duration is divided
  between the middle image and the return. Each section must retain at least one frame.

A single description is reused throughout FMF. Separate descriptions stay in
scene order; if a later description is missing, the last supplied one is reused.
Technical capacity splits keep the scene's reference image and prompt. The loop
report shows the resulting cut times. Saved runs retain their resolved FMF plan,
images and prompts on Resume, including later Part Prompt Editor changes.

FMF is a native H3 scene assignment, not a visible crossfade or an extra image
keyframe inside one render. Each scene still renders at least 124 frames before
padding is removed. Use short manual intervals for a brief preview; equal thirds
give the alternate image a third of the video. This mode does not change lip-sync
image assignment or scene-detector sensitivity.

The conditioner places the last image at the **retained** endpoint, even when
the model renders padding beyond it. A one-frame part with both references uses
the first image, since both endpoints cannot occupy distinct frames.

For reference-video descriptions, use **Scene Motion Analysis** with appearance
**exclude** when images supply appearance. Use **Scene Description (T2V)** with
appearance **include** for full textual descriptions. These task choices remain
explicit in Smart LM and Scene Analysis to H3.

Load Image Timeline's slot blends affect its still-image renderer. They do not
blend generated H3 clips. Such transitions require a separate edit after
generation; keeping the audio clock requires replacing frames around each cut
without shortening the timeline.
