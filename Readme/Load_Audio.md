# Load Audio

Load Audio [Eclipse Nova] selects an excerpt from an uploaded file or incoming AUDIO,
with an in-node player and an optional **Stop** control.

## Panel controls

**Load Audio [Eclipse Nova]** uses the shared node design in classic canvas
and Nodes 2.0.

- The collapsible **Source** bar selects **Auto**, **File** or **Input**.
  **Stop** is the square at the right; it defaults off and retains the same
  review-and-continue behavior described below. Playback stays in the audio player.
- The searchable filename picker reads the current input-folder list whenever
  it opens. **+** uploads audio or video; files can also be dropped on the panel.
- The collapsible **Trim** section contains start and duration in seconds.
  Zero duration means the remainder of the source. Both sections remember their
  collapsed state without changing execution settings.
- The player retains precise seeking, clip-relative timestamps, immediate source
  switching and full-source audition after incoming audio has executed once.

| Input | Purpose |
| --- | --- |
| `audio_in` | Incoming AUDIO. Auto prefers it; File ignores it and does not request its upstream execution. |
| `start_time` | Optional FLOAT overriding the local start, including an explicit zero. |
| `duration` | Optional FLOAT overriding the local duration, including zero for “to end.” |
| `enabled` | Optional BOOLEAN. False skips loading and the execution preview; connect Video Run Storage's `prepare` output to read sources only for New run. |

Unconnected or `None` trim inputs use the local values. A connected trim input
disables its local field; the header summarizes resolvable input values. Computed
inputs still need execution before their actual trim can be auditioned.
The outputs remain **audio** and the **actual duration** in seconds, preserving
sample rate, channels, batches and incoming sample values.

For lip-sync generation, use one loader for the full song and a second for the
video excerpt. Connect a shared Float to the second loader's `start_time` and
to caption trimming so both select the same starting point. Set the excerpt
length in the panel or through the optional `duration` socket.

In a resumable loop, connect the first loader's full recording to Video Loop
Start's `caption_audio` and the excerpt start to `caption_start`. The run saves
both for later captions. Connect `prepare` to both audio loaders' `enabled`
inputs so Resume/Load do not reopen the original files. File availability is
checked when an enabled loader executes if its enable control is connected.

## Visual tour

![Load Audio with File selected, one-second start and a four-second sample excerpt](assets/nova-load-audio.png)

The panel example uses a short recording. To build the full-song and excerpt
branches below, keep the incoming song whole in the first node, then select
the video excerpt in the second.

```mermaid
flowchart LR
    song[Generated AUDIO] --> full[Load Audio: full song]
    full --> clip[Load Audio: trimmed excerpt]
    start[Shared start in seconds] --> clip
    start --> captions[Caption trimming]
    clip --> video[Video generation]
```

1. Feed the incoming AUDIO into the first node's `audio_in`. **Auto** uses that
   input; `start_time = 0` and `duration = 0` retain the full song. Keep this
   node's `audio` output available for full-song saves and caption alignment.
2. Connect the first node's `audio` output to the second node's `audio_in` and
   choose **Input** there.
3. Connect a Float containing the desired start in seconds to the second node's
   `start_time`, and set its `duration` to the desired excerpt length. Share the
   start value with caption trimming so the video and captions select the same
   excerpt.
4. Enable **Stop** on the second node to audition the clip.
   Queue unchanged again to continue, using its `audio` and actual `duration`
   outputs for the video branch and its duration/planning consumers.

For a five-minute sample, the first player retains `300` seconds
and the second can preview `238` seconds. Change the shared start and clip duration
to select another excerpt from your song.

## Source, trim and review controls

For generated songs, connect the generator's full AUDIO to both your full-song
Save Audio node and Load Audio's optional `audio_in`. If the save node passes
AUDIO through, you can connect that output to `audio_in` instead. Connect Load
Audio's trimmed AUDIO to lip-sync and **every audio duration/planning consumer**
in the video branch. Its second output reports the actual excerpt duration in
seconds. Saving the generator's output keeps the saved song full length.

1. Choose **Source**: **Auto**, **File**, or **Input**.
   Select or upload a file when using the file source, and connect generated
   audio to `audio_in` if desired.
2. Set `start_time` and `duration` in seconds. A duration of `0` means to the end;
   an oversized duration stops at the end. Empty excerpts are rejected.
3. Enable **Stop** and queue. Load Audio executes even without a
   downstream consumer, publishes its preview, and stops downstream execution.
4. Audition the excerpt. Change start/duration and use the precise seek slider
   without queueing. The time display is relative to the excerpt. These edits
   change the preview immediately; they change downstream AUDIO on the next run.
5. Queue unchanged again to continue from the reviewed excerpt, or disable the
   stop and queue to release it to lip-sync.

Connected numeric primitives control the preview too: editing their value
refreshes the excerpt without queueing or starting video generation. Load Audio
follows numeric primitives, reroutes, Eclipse Set/Get, and resolvable subgraph
inputs/outputs, including promoted trim widgets. It restarts at the excerpt's
beginning and keeps the playing or paused state. Local trim fields apply only
when their inputs are disconnected.

If a connected value needs backend computation, the player reports **Trim
requires execution**. After execution it can audition the last computed trim,
identified as coming from the last run; it does not substitute the local
widget value. Changing the graph still requires a new run for computed values.

**Source** changes the player without queueing:

- **Auto** prefers incoming AUDIO. Muting the connected source restores the file
  preview while the cable stays connected. Bypassed sources
  use incoming audio when an AUDIO path remains; otherwise they fall back to the
  file. This also follows reroutes and Eclipse Set/Get connections.
- **File** immediately previews the chosen file even with `audio_in`
  connected. On the next queue, Load Audio uses the file without requesting its
  upstream input. Other output nodes can still request that upstream branch.
- **Input** requires a usable input and reports when it is unavailable.
  It never silently selects the file.

The file dropdown and upload button remain available while using incoming audio.
Switch to **File** to play the selected file. Source and trim
changes affect downstream AUDIO on the next queue. New generated audio needs one
execution before its preview exists; previously generated audio can be auditioned
immediately. Custom routers whose output depends on execution may still need a
queue for automatic fallback; use **File** to override them immediately.
Invalid incoming AUDIO raises an error instead of silently switching songs.

The source label identifies incoming audio or the selected fallback file.
Incoming previews contain the **full source**, so any excerpt can be auditioned
after one execution. A batch previews its first item; all batch items and channels
are preserved in the output. Browser previews use 16-bit PCM; the downstream
tensor retains its original samples, dtype and sample rate without resampling.

Incoming previews are temporary and are never used as a fallback song. Changing
the input connection clears the old preview. If a preview disappears after a
restart, queue again; the saved fallback selection and trim settings are retained.

An unchanged review queue can continue using ComfyUI's cache. Changed inputs
require review again; randomized seeds or upstream cache policies can regenerate
the song.
