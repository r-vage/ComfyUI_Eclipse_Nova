# MiniMax H3 native clips

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
| adjacent_pairs | Images 1→2, 2→3, etc. per part; after the images are exhausted, the final image anchors the start |
| reference_images | Up to 9 enabled images supply native visual references without fixing the first or last frame |
| text_only | Ignore connected images and generate from the prompt |

In **reference_images**, prompt tags such as `<Picture 1>` identify images in
their enabled timeline order. When the prompt contains no picture tags, the node
adds a short direction to use the supplied images as visual references. With no
images, it uses text-to-video-and-audio. **text_only** ignores images even when
the loader is enabled; muting the loader also avoids loading them.

Scenes come from cut times or the untimed prompt list. Image slots do not create
scene boundaries themselves. Capacity splits retain the same scene number, so
**first_per_scene** and **adjacent_pairs** keep the scene's image assignment
throughout those renders. Clips remain independent generations; reusing an image
does not guarantee continuous motion or generated sound across their joins.

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
