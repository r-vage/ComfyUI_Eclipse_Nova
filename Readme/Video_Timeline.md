# Video Timeline

Open `Unified_Video_Timeline_Nova.json` in the ComfyUI workflow library. Choose the render path and duration in **Video Timeline Planner**. Its report gives the retained frame count, duration and number of render parts before sampling.

| Render path | Timing and guidance |
| --- | --- |
| Native H3 | 24 FPS. Supports text only, first-frame, first-and-last and active-reference guidance. H3 can generate its own audio. |
| H3 lip-sync | 24 FPS. Uses a reference image and vocal guide. First-and-last bridges into the next scene. Active reference reuses the current image on a capacity split. |
| WAN InfiniteTalk | 25 FPS. The first loop task renders the opening. Each extension uses the preceding motion frames and the corresponding position in the vocal track. The default context is 81 frames and the overlap is 9. |

Select the preset yourself on **Shared video model loader**. The usual choices are `MiniMaxH3_TFL2VA` for Native H3, `MiniMaxH3_LipSync` for H3 lip-sync and `Wan_Lipsync` for WAN InfiniteTalk. For an existing run, use **Preview run report** to look up the preset you used. To change optional H3 LoRAs, use **H3 LoRA stack**. WAN has its own InfiniteTalk patch and speech encoder. MiniMax Music 3 and YuE2 each keep a loader in their music group.

## Reference images at scene cuts

Enable the pictures in **Load Image Timeline** in the order you want to use them. In **Video Timeline Planner**, **image_assignment** selects the picture for each scene. **guidance** controls how the generator uses it.

| Image assignment | Example with three enabled pictures |
| --- | --- |
| Per source clip | One source video uses picture 1 for all its scenes. A second source video starts with picture 2. Older workflows open with this setting. |
| In order at scene cuts | Scenes begin with 1, 2, 3, 3, 3. The last picture stays selected for the remaining scenes. |
| Cycle at scene cuts | Scenes begin with 1, 2, 3, 1, 2, 3. |
| Equal time at scene cuts | The planner aims for one third of the total duration per picture. Each change uses the nearest available cut that leaves a scene for each remaining picture. An exact tie uses the earlier cut. |

The cut-based choices use the existing scene boundaries. A source video with no cuts stays one scene. With fewer scenes than pictures, equal-time assignment uses the first pictures in order. Render-capacity splits and warmup frames stay within the same scene.

Choose **First frame** to start each scene with its assigned picture. For either H3 path, **First and last** with **Cycle at scene cuts** guides successive scenes from 1→2, 2→3, 3→1 and repeats, including the final scene. **In order at scene cuts** gives 1→2, 2→3, then 3→3. Equal-time guidance targets the next scene's assigned picture and holds the final picture at the end. WAN InfiniteTalk takes one reference per scene. The planner report and **Preview run report** show the picture numbers in scene order. Use **New run** to apply a different assignment to a completed video.

## Duration and audio

| Duration source | What the seconds control means |
| --- | --- |
| Source clip lengths | The loaded video's clip lengths determine the duration. |
| Audio track length | The selected duration track determines the duration. |
| Seconds per clip | Each source clip gets the entered duration. |
| Total seconds | The entered duration is shared across all source clips. |

Under **Conditioning audio and final soundtrack**, select the duration track, vocal guide and soundtrack independently. With **Recording or video**, these switches determine which recording they use.

| Enabled in Optional sources + analysis | Recording used |
| --- | --- |
| YuE2 alone | The YuE2 song |
| MiniMax Music 3 alone | The MiniMax Music 3 song |
| Audio override with **Selected file** | The selected file and its trim, including when a music group is enabled |
| Audio override with **Auto** | The enabled generator's song when available, otherwise the selected file. The second Load Audio node applies the shared trim. |
| Only Reference video | The video's embedded, unmuted audio |

Enable one music generator at a time. Its song works with **Audio override** switched off. If both generators are enabled, the video takes YuE2 first and both music groups can still render their songs.

H3 lip-sync uses the selected recording for its audio guide, and WAN InfiniteTalk passes it to the speech encoder. Both export the selected final soundtrack. Native H3 uses the selected recording as its final soundtrack and generates motion from its visual conditioning.

**Source clip lengths** keeps the video's timing when you replace its audio. **Audio track length** follows the duration track. To use the clip's own audio for lip-sync while exporting another recording, choose **Reference video** in **Conditioning track**. A short vocal guide is padded with silence. A short soundtrack repeats to fit. Select **None** for the final soundtrack to keep native H3's generated audio or produce silent lip-sync video.

**Skip tail frames** defaults to zero and preserves the planned duration. A positive value drops the last technical continuation if its retained length is at or below the threshold. An explicit final scene is always kept. For example, with WAN's 81-frame context, an 82-frame single scene keeps all 82 frames at zero and keeps 81 at a threshold of one.

## Scenes and prompts

The workflow opens with manual scene directions. Enter the global prompt once and one scene direction per line in **Wildcard Processor**, starting with scene 1. Enter cut times in seconds on the reference video's clock when connected, or on the output clock otherwise. **Live analysis** in the source controls can supply measured cuts and scene descriptions.

Enable **Optional Smart LM** to describe each scene from its local direction and available image. **Apply global direction to every scene** adds the exact text from **Global direction for every scene** after scene analysis and optional description. For H3 lip-sync, singing and lip-sync directions appear in the visual description and `overall_soundscape` starts at `N/A` because the run uses the supplied audio. Native H3 can keep its generated soundscape.

**Final generation prompts** shows the assembled text for each scene. Enable its pause control to edit any part before sampling, including its global direction and audio fields. The run saves the reviewed text, including line breaks. A capacity split keeps the same scene prompt and source image.

For native H3 **First and last**, the end picture guides the last retained frame of the scene. A technical continuation reads its motion guide from the preceding part. H3 lip-sync places its end guide immediately after the retained frames so the next scene starts on the cut. Native H3 passes its sampled video and audio latents through **Eclipse KSampler Advanced** with **Decode** off, so each stream reaches its own decoder.

## Lyric captions

Use **Lyric transcript and corrections** to transcribe the recording, isolate vocals or enter wording and full-song timing corrections. Both lyric groups can use those inputs. Each has its own switch and appearance controls.

- In **Black lyric timing test**, enable **Timing preview** and press **Play** on **Preview black lyric test**. It plays the captions over black for the selected recording or saved excerpt. You can adjust the corrections and replay this node on its own.
- In **Final lyric overlay**, enable **Final lyric overlay** to caption the generated, loaded or upscaled footage on export. The black preview can stay off.

## Saved runs

Enable **Disk timeline** and **Keep files** to reopen a run after restarting ComfyUI. **Parts per queue** limits how many new parts are rendered per submission. **Stop after current part** saves the completed part.

Click **Refresh runs** in **Load Video Run**, choose the run or a backup, then click **Preview run report**. The report shows the saved video task, loader preset and model filename before you queue anything. New persistent runs record the selection when queued. Older runs use their archived workflow and prompt when available. Missing details appear as **Not recorded**. Choose the preset on **Shared video model loader** before resuming or regenerating a part. Select **Resume saved run** to continue from the next part, or set **Restart part** to regenerate from a specific 1-based part number.

On **New run**, **Part Prompt Editor** clears the previous run and follows the current render part once the plan is ready. **Reset editor** clears the displayed prompts and pending edits.

For a one-part change, choose **Update selected run** and the part number. Read the saved prompts in **Part Prompt Editor**, enable the edit and queue. The other parts keep their saved media. **Load Video Run → Backup** opens the version from before the update. The original three workflows continue to use their serialized Nova node IDs. Their superseded planners and helpers appear under **🌒 Eclipse Nova / Legacy**.
