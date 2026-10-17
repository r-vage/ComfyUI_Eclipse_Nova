# Image conversion, mask cropping and system recording

**Image Convert**, **Image Crop by Mask** and **System Audio Recorder** use
Nova's selected design in both classic canvas and Nodes 2.0. Their serialized
IDs end in `[Eclipse Nova]`.

Bars collapse to a summary of the selected options. Collapsing a bar or section
does not disable its settings. Section pins keep several sections open;
presentation and values survive workflow save/reload.

## Image Convert

Connect an IMAGE to `images`. The Conversion bar independently enables **RGB**,
**Grayscale** and **Composite alpha**. With all three disabled and Style set to
`none`, the image passes through unchanged.

Composite alpha reveals a native background color picker. Operations run in this
order: composite transparency, convert to RGB, convert to grayscale, then apply
the selected style. Grayscale produces three equal channels for ComfyUI IMAGE
compatibility. RGB without compositing discards alpha. The searchable Style menu
contains the existing pilgram filters; all images in a batch are processed.

## Image Crop by Mask

Connect `image` and `mask`. The Mirror bar offers None, Horizontal, Vertical and
Both. The sections contain:

- **Output size:** width, height, divisibility, resampling and device. Optional
  `target_width` and `target_height` inputs override the corresponding local
  value when non-None. Dimensions round upward to the selected multiple;
  divisibility `0` disables rounding.
- **Framing:** zoom and rotation. Zoom `1` fits the mask, values below `1` include
  more context, and values above `1` crop closer. Positive rotation is clockwise.
- **Mask:** threshold and output blur. Threshold determines the crop bounds;
  blur softens the final mask without changing the image framing.

An empty mask frames the full image. A single mask can serve an image batch, and
a single image can serve a mask batch. Each output list item retains its batch
dimension. Areas outside the source image are black and remain masked for
inpainting. The existing tensor resampler uses Bicubic for the Lanczos option.

## System Audio Recorder

The Format bar selects WAV, WAV + MP3 or MP3 and toggles **Trim silence**. Output
contains the filename prefix and, for MP3, bitrate. Enabling Trim silence adds
the Leading silence section with its dBFS threshold.

Open **Output device** or use its refresh button to read the current device list.
Saved selections retain the device ID. Loading an idle node does not enumerate
devices or start recording.

1. Connect `audio` to the downstream workflow and choose the output settings.
2. Press **Start** to begin capture and submit the workflow. Settings are locked
   during capture; execution waits at the recorder.
3. Press **Stop** to finalize the requested files and let downstream execution
   continue. This does not cancel the queue.
4. Change the output or silence settings and press **Update Output** to publish
   another version from the retained capture and queue again.

The outputs remain `audio`, `wav_path`, `mp3_path` and `duration`. Capture stays
48 kHz stereo. Published files remain intact when a session is released. A
retained recording can be restored while the same ComfyUI process is running;
restarting the server requires a new capture.

Status polling runs during active capture and stops when the recording is ready.
Rejected submissions and execution interruptions abort an active capture.
Deleting the node releases its private recording source.

See the [System Audio Recorder guide](System_Audio_Recorder.md) for supported
platforms, trim behavior and file handling.
