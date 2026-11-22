# Eclipse loops

**Loop Start**, **Video Loop Start** and **Loop End** execute sequential work using
ComfyUI graph expansion. They do not require Easy-Use. They carry one value,
including an intact list, tuple, PIPE, frame timeline or VIDEO.

## Analysis and other sequential work

Connect Start's **loop** to End's **loop**, its **index** to the iteration's work,
and its **previous** to the input that accumulates results. Feed the completed
iteration result to End's **value**. End expands another iteration or returns the
accumulated value, next index and completion status.

- **total** is the exclusive ending index. Zero returns the initial value.
- **start_index** is absolute. Provide matching **initial_value** when starting later.
- **parts_per_queue** limits completed iterations; zero means all remaining.
- **cache_iterations** reuses unchanged work. Disable it to rerun every queue.
- End's **block downstream** prevents partial results reaching a consumer that
  requires complete coverage, such as Save Scene Analysis.

Only dependency paths between Start and End repeat. Connect any per-iteration
preview or side effect before End; an unrelated output is not automatically
part of the loop. Get/Set routing works after normal frontend link resolution.

## Video rendering and recovery

Use **Video Run Storage** to choose **New run**, **Resume saved run**,
**Update selected run** or **Load saved run**, and RAM, temporary disk or persistent output. For resumable
runs, enable **Disk** and **Keep files**.
New run creates a new run on each queue; choose Load saved run for downstream
caption or export changes that should reuse completed media.

```mermaid
flowchart LR
    Inputs[Resolved plan, images, prompts and audio] --> Start[Video Loop Start]
    Saved[Load Video Run] --> Start
    Start --> Render[Condition and sample one part]
    Render --> Append[Append retained frames or clip]
    Append --> Preview[Accumulated preview]
    Preview --> End[Loop End]
    Start -->|loop| End
    End --> Final[Captions or final export]
```

Connect Load Video Run's **source** and **run_path** to Start's **previous** and
**run_path**. It is requested on Resume and Update. The saved-run dropdown
chooses the folder; the loader's **backup** selector can preview an earlier version
inside it. Connect fresh resolved inputs for New run, then use Start's
outputs for downstream conditioning, dimensions, prompts, reference images,
audio, reference mode and storage. These outputs come from the saved checkpoint
on resume. Start's **index** includes retained parts and goes directly to both
the conditioner and **Video Part Seed**.

Feed **Seed → Video Part Seed → RandomNoise** independently of loaders and
conditioning. Changing it before the next queue affects new/replacement parts.
Model, LoRA and sampling settings remain those selected in the workflow; choose
the matching lip-sync/native mode. Loaded model objects are not checkpointed.

The append node commits each completed part before the accumulated preview runs.
Keep the full soundtrack on the lip-sync preview. This shows the join between
the retained prefix and new part, including the frames left after warmup trimming.
Connect Start's **render** through Video Run Gate to independent body previews
so a completed resume with no new parts does not request sampling.

**Stop after current part** finishes that save and preview before returning.
For a loop inside a subgraph, put **Loop Control** on the main canvas and connect
its **control** output to Start's optional **stop_control** input. Get/Set can
carry this connection between groups and into the subgraph. Connect it before
queueing, then click the external button while the loop runs. Both it and the
button on Start show the stop request; either can be used. This is a live request,
so it does not require queueing again or changing a generation input. Use one
control per independently running loop. An idle button has no effect, and stop
requests do not carry over to the next queue.

**Parts per queue = 1** provides the same review point after one new part. Select
the resulting saved run and choose Resume for the next queue. **Restart part = 0**
continues; **N** keeps parts 1 through N−1 and replaces N onward. Persistent resume
creates a new revision and leaves the original files intact. End reports its
saved path. A completed resume returns the existing result without sampling.

### Replace one part and keep the ending

Choose **Update selected run** in Video Run Storage and set **Restart part**
to the saved part's number, starting at **1**. The loop restores the selected run's
inputs, generates exactly that part, then reattaches the later saved parts before
returning its result. **Parts per queue** does not change this one-part scope.

For part 13 of a 34-part run, the updated run contains original parts 1–12,
the new part 13, and original parts 14–34. Keep **Disk + Keep in output** enabled
and the loader's **backup** on **Current run**. The same folder stays selected for
the next correction; its previous version is saved as a backup.
Reused parts retain their exact media and generation seeds;
the replacement keeps its saved duration, canvas, FPS and audio placement.

Use Part Prompt Editor to change only the selected part's prompt, and change the
render seed if desired. Pending edits to other retained parts must be cleared;
their saved prompts must continue to describe their saved media. Existing saved
edits are preserved. Native generated audio remains in each retained clip; an
external master soundtrack stays unchanged.

The selected part must already exist. A partially completed run keeps all of its
saved parts and remains partial; ordinary Resume can later generate its unfinished
ending. If an update is interrupted or fails, its current version stays intact;
keep **Current run** selected and queue Update again.

When the following lip-sync part used generated continuation, it still contains
motion based on the old part. The planning report identifies this case; review
the join after replacing. The mode always preserves that following part.

### Update the same run and restore a backup

Choose **Update selected run**, enable **Disk + Keep in output**, and leave the
loader's **backup** on **Current run**. Set **Restart part = N** to an already saved
part and queue. Exactly that part is regenerated and every other saved part is
retained. The selected folder stays the same, so the next correction builds on
the updated run without refreshing or choosing another folder. **Parts per queue**
does not change the one-part scope.

The update becomes current only after its replacement and retained ending are
valid. Before switching, the previous media, prompts, seeds, checkpoint and
workflow metadata are saved under `.backups/` inside the run. Interrupted or failed
updates leave the current version available; keep **Current run** selected and
retry. If another operation updates or restores the run during rendering, the
older operation cannot overwrite it.

In **Load Video Run**, click **Refresh runs** to refresh the backup list. Choose a
backup and use **Load saved run** to preview/export it, or **Read selected run** to
inspect its prompts. Selecting a backup does not change the current run. Click
**Restore selected backup** to make it current without generation. Restore backs
up the version it replaces, returns the selector to **Current run**, and reloads
connected prompt editors with pending edits reset and Apply off. The previous
editor draft remains available through workflow undo. To edit a backup, restore
it first; backups themselves are read-only.

Both complete and partial runs are supported; restoring a partial backup restores
only its saved parts. Ordinary Resume can generate the unfinished ending. Backups
start with the first Update; older sibling run folders remain separate runs.

Keep the entire run folder when moving it. `run.json` points to the active media
and checkpoint inside `.versions/`; root-level metadata from the initial run is
historical after an update. Unchanged media uses hard links where supported, with
copies as a fallback. History is retained until you remove the run; do not delete
individual files or hidden folders that a current version or backup may need.

### Edit the prompt for one render part

Connect Load Video Run's **run_path** to **Part Prompt Editor → run_path**, and
the editor's **prompt_edits** to Start's optional **prompt_edits** input. Both
connections can use Get/Set, including when Start is inside a subgraph. The editor
uses the loader's existing selection; it has no second run picker.

When **New run** executes, the connected editor clears the previous prompts and
drafts. Once the plan is ready it shows the current part's resolved prompt and
advances with the loop. You can browse other parts with the dropdown and arrows.
The live text is read-only because this render already has its prompts.

1. Select the saved run, then click **Read selected run** in the editor. This reads
   prompt text and part ranges without loading models, references or audio arrays.
2. Choose the **Render part** from the themed dropdown or use **◀ / ▶** beside it.
   Switching parts preserves pending edits; arrows stop at the first and last part.
   Edit its prompt. Numbers match **Restart part**;
   a long scene may span several render parts with independently editable prompts.
3. Enable **Apply edits**, choose **Resume saved run**, and set **Restart part**
   to the earliest completed part you changed. Leave it at `0` for upcoming parts.
4. Set **Parts per queue = 1** to review the replacement and its transition, change
   the render seed if desired, then queue.

The field contains the combined global and scene text for that part. Its edit
**replaces the full prompt**, so conflicting original instructions are not added
back. Keep any global direction or native H3 sound instructions you still want.
Reference-image conditioning, timing, audio selection and lip-sync warmup remain
as saved. Unedited parts keep their original prompts. **Resume saved run** renders
from N onward. To keep the later media, choose **Update selected run** for the same
folder with backups and edit just the selected part as described above.

Resume saves the edited plan with its new persistent revision, including changes
to upcoming parts. Select that revision to continue. Update saves its corrected
prompt in the selected run. Corrections remain even when Apply edits is off.
**Read selected run** reloads the saved text, selects the first part and clears
pending edits. **Reset this part** restores that part's saved text. **Clear edits**
discards pending changes and switches Apply off. **Reset editor** clears the
displayed catalog as well. Changing the saved run or backup clears the previous
selection's text. These controls leave the saved files intact.
Update automatically reloads the saved prompts in connected editors. If the run
changed since a draft was read, read the selected version again before applying
new changes.

Queueing captures the edits. Stop first to change a prompt for the next queue.
Editing the ordinary upstream prompt boxes affects New run; use this editor to
change a saved run. Older media-only runs need a render checkpoint for editing,
as they do for Resume.

### Routing saved results

Route **Load saved run** around Start directly to final output. Use Storage's
**generate** output for the generated-versus-loaded selector and its **prepare**
output to gate independent source/analysis/planning outputs. Otherwise those
outputs can request work even when Start restores saved inputs. Get/Set can carry
these values between groups without physical cross-group connections.

Video Loop Start also blocks its outputs in Load mode without requesting fresh
inputs, so an independent loop preview cannot start planning. For Load Audio's
own output/preview, connect Storage's **prepare** to **enabled**. Video Run Gate
accepts a missing optional value and passes `None` while enabled, allowing muted
optional vocals to remain connected to a consumer's optional input.

For captioning an excerpt, connect the complete recording and its excerpt start
to Start's **caption_audio** and **caption_start**. They are saved with persistent
checkpoints. Select **caption_context** from Loop End or Load Video Run along
with the selected video, and feed it to **IO Lyric Captions → pipe**. Connect the
video as **background** and its actual duration as **duration**. The full recording
is trimmed once; current source controls cannot change a resumed run's offset.
Without a supplied soundtrack, IO Lyric Captions reads the VIDEO's generated
audio. Older checkpoints without this context use the saved soundtrack from zero.

Each persistent run contains `checkpoint.json`, resolved input arrays and
`run.json` with the committed media parts. Move the whole folder under ComfyUI
output and refresh the run list to reuse it. Old runs without a render checkpoint
remain loadable/exportable; their resume inputs are not reconstructed from
workflow snapshots. An interrupted sampling pass restarts the unfinished part.
RAM and temporary runs retain their normal cache lifetimes.

Generic analysis loops do not save partial LM progress across restarts. Video
checkpoints save the resolved prompts after analysis has completed. See
[scene analysis](Scene_Analysis.md) and [saved media](Frame_Timeline.md) for details.
