# Video Timeline

The Unified Video Timeline workflow is distributed separately on Civitai. To follow this guide with Nova.2, open `Unified_Video_Timeline_Nova.2.json` in ComfyUI. [Workflow release page](https://civitai.red/models/3061803/lipsync-minimax-h3-wan-infinitetalk-h3-native-tfl2va)

Choose the render path in **Video Timeline Planner** and the duration mode in **Video Timeline Duration**. The planner report gives the retained frame count, duration and number of render parts before sampling.

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
| Seconds per clip | Keep up to the entered duration from the beginning of each trimmed reference clip. At 15 seconds, clips lasting 8 and 25 seconds contribute 8 and 15 seconds. Without video, use the entered duration for each planned clip. |
| Total seconds | Keep the first entered number of seconds of the joined reference playlist. With the same clips and a 15-second limit, use 8 seconds of the first and 7 of the second. Without video, use the entered duration for the whole plan. |

The workflow takes **seconds** from **Smart Folder → Video → Duration**. In either numeric mode, `-1` keeps all available reference footage. Load Video applies the range before cut detection, scene sampling and embedded-audio extraction. A cut at the endpoint belongs to the excluded footage. A scene crossing the endpoint is described using only its retained frames. Start a **New run** with **Live analysis** to generate descriptions for a changed range.

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

**H3 shot mode** on **Video Timeline Planner** controls how Native H3 and H3 lip-sync render those directions.

- **Separate at cuts** is the default. Each cut starts a new render part on its planned frame. Choose this when a cut must land on a particular frame or you want to regenerate a short shot independently.
- **Group timed shots** fits up to 15 visible seconds of consecutive shots with the same assigned image into one render. The planner numbers the shots and gives later shots cut times on that render's clock, for example `[Shot 2] At 00:01.208, the shot cuts.` H3 interprets these cues, so an internal cut can move or be missed. A change of image, a source playlist join, or a shot that would exceed the available frames starts another group at a cut. Warmup and any required end-guide frame count toward the capacity.

With a 362-frame capacity, zero opening warmup and one reference image, 15 seconds at 24 FPS can fit in one part. H3 renders 362 frames and the timeline keeps 360. The optional writer still receives each original shot separately. The planner combines its descriptions and applies the global direction once per grouped prompt. WAN InfiniteTalk uses its own scene transitions.

**Final generation prompts** shows one item per separate scene or H3 shot group. Enable its pause control to edit a shot's text within that item before sampling. The run saves the reviewed text, including line breaks. Replacing a saved part regenerates every shot in that part. A capacity split within a long single shot keeps its prompt and source image.

For native H3 **First and last**, the end picture guides the last retained frame of the scene. A technical continuation reads its motion guide from the preceding part. H3 lip-sync places its end guide immediately after the retained frames so the next scene starts on the cut. Native H3 passes its sampled video and audio latents through **Eclipse KSampler Advanced** with **Decode** off, so each stream reaches its own decoder.

## Transitions between scenes

**Video Transition to Next** in the **Scene transitions** group controls the boundary after an authored scene. **After scene** `0` sets the default. To change only the transition from scene 2 to scene 3, duplicate the node, connect the first node to the copy's **previous** input, set **After scene** to `2`, and connect the copy to the planner. These controls also work with text-only Native H3.

- **Shot** defaults to **Cut**. **Continue shot** gives grouped H3 prompts a timed change of action in the same shot. Across separate renders it uses up to 22 retained motion frames when guidance permits. **Active reference** keeps the incoming picture alongside the motion guide. **First and last** can carry motion from an A→B clip into a B→C clip while keeping B on the incoming first frame and C as its endpoint. A switch to a different **First frame** starts from the newly assigned picture.
- **Previous prompt influence (%)** defaults to `0`. For example, `25` uses 25% of the previous reviewed prompt and 75% of the incoming reviewed prompt for the first incoming render. Later parts use their own prompt at full strength. At `100`, the previous direction supplies all of the text conditioning. Each blend reads the actual edited text from the prior part. A weighted scene gets its own render even in **Group timed shots**.
- **Picture transition** and **Picture transition seconds** select a cut, fade, dissolve, wipe or another listed effect. The effect is centered on the cut and shortened to fit the adjacent scenes. When the assigned image changes, **Blend to next** on the outgoing **Load Image Timeline** slot supplies the picture effect. **Inherit** uses the default, and a numbered scene override takes priority over the image slot.

H3 lip-sync follows the cuts and playlist joins of an edited reference video. Across those boundaries it uses the full incoming prompt and its normal visual guides. WAN uses its existing motion and prompt handling. Both paths accept picture effects, with the vocal guide, soundtrack and output duration on their original clocks.

The planner and saved-run reports list the resolved transitions. Preview and export apply picture effects to the assembled frames. Stored parts retain their original pixels for continuation, replacement and resume. Reloading a run or backup restores its resolved settings.

## Lyric captions

Use **Lyric transcript and corrections** to transcribe the recording, isolate vocals or enter wording and full-song timing corrections. Both lyric groups can use those inputs. Each has its own switch and appearance controls.

- In **Black lyric timing test**, enable **Timing preview** and press **Play** on **Preview black lyric test**. It plays the captions over black for the selected recording or saved excerpt. You can adjust the corrections and replay this node on its own.
- In **Final lyric overlay**, enable **Final lyric overlay** to caption the generated, loaded or upscaled footage on export. The black preview can stay off.

## Saved runs

Enable **Disk timeline** and **Keep files** to reopen a run after restarting ComfyUI. **Parts per queue** limits how many new parts are rendered per submission. **Stop after current part** saves the completed part.

Click **Refresh runs** in **Load Video Run**, choose the run or a backup, then click **Preview run report**. The report shows the saved video task, loader preset and model filename before you queue anything. New persistent runs record the selection when queued. Older runs use their archived workflow and prompt when available. Missing details appear as **Not recorded**. Choose the preset on **Shared video model loader** before resuming or regenerating a part. Select **Resume saved run** to continue from the next part, or set **Restart part** to regenerate from a specific 1-based part number.

On **New run**, **Part Prompt Editor** clears the previous run and follows the current render part once the plan is ready. **Reset editor** clears the displayed prompts and pending edits.

For a one-part change, choose **Update selected run** and the part number. Read the saved prompts in **Part Prompt Editor**, enable the edit and queue. The other parts keep their saved media. **Load Video Run → Backup** opens the version from before the update. The original three workflows continue to use their serialized Nova node IDs. Their superseded planners and helpers appear under **🌒 Eclipse Nova / Legacy**.
