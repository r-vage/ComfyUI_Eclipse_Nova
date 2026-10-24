# Save Images [Eclipse Nova]

Save images with generation metadata, placeholder-based paths and filenames, and seven output formats. The themed panel provides compact controls and a resizable batch preview.

## Panel

![Save Images with Save and Preview enabled, Format controls and an actual saved sample-image preview](assets/nova-save-images.png)

The node works in classic canvas and Nodes 2.0 and follows the selected Eclipse Nova node design.

- **Mode:** Save and Preview toggle independently. Disabling Save uses temporary PNG previews; it does not write to the configured output directory.
- **Output:** custom path, filename prefix, delimiter, counter digits and counter placement.
- **Format:** PNG, JPG, JPEG, GIF, TIFF, WebP or BMP, with applicable quality, DPI, optimization and lossless controls.
- **Metadata:** embedded workflow, PNG generation data, optional LoRA tags, prompt removal from generation parameters, and workflow JSON sidecars.

Sections start collapsed. Pin a section to keep it open while opening another. Inactive settings remain in the workflow. Resize the node to resize the preview; batches retain the adaptive grid and image navigation.

**Custom DPI** is available under Format for JPG/JPEG, PNG, TIFF and BMP. It is off by default; enable it to write the selected print resolution (initially 300 DPI) on both axes. This changes print-size metadata without resizing the pixels. GIF and WebP do not show this control. With Custom DPI off, PNG, TIFF and BMP retain their normal format defaults; JPEG keeps its existing 300 DPI default.

The sockets are `images` and `pipe_opt`, both optional; at least one must supply images. Outputs remain the input images and the saved `files` list. Preview-only mode returns an empty files list.

### Pipe destination priority

**Save Images** reads these values separately from each image's pipe:

| Setting | Priority |
| --- | --- |
| Output directory | Non-`None` `output_path`, then non-`None` `path`, then the local Output settings |
| Filename prefix | Non-`None` `filename_prefix`, then the local filename settings |

Pipe values take priority even when Custom path or Custom filename is off. Missing or `None` values leave the local settings active. An empty path explicitly selects the ComfyUI output directory. Placeholders work in pipe strings too.

**Smart Folder** already supplies `path`. **IO Generation Data** accepts and preserves `path`, `output_path` and `filename_prefix`; **IO Context Image** preserves these too. Connect strings to those pipe inputs, then connect the resulting pipe to `pipe_opt`. Nodes that rebuild their own pipe must preserve these keys if placed in between.

```text
Smart Folder: pipe ───────────────→ IO Generation Data: pipe
String: "portraits/%seed" ───────→ IO Generation Data: filename_prefix
                                  IO Generation Data: pipe ─→ Save Images: pipe_opt
decoded images ────────────────────────────────────────────→ Save Images: images
```

## Table of Contents

- [Panel](#panel)
- [Inputs and settings](#inputs-and-settings)
- [Placeholder System](#placeholder-system)
- [Output Formats](#output-formats)
- [Metadata Embedding](#metadata-embedding)
- [Preview-Only Mode](#preview-only-mode)
- [Pipe Integration](#pipe-integration)
- [Outputs](#outputs)
- [Usage Examples](#usage-examples)
- [Tips & Best Practices](#tips--best-practices)

## Inputs and settings

| Input | Type | Description |
| --- | --- | --- |
| `images` | IMAGE | Optional direct image input |
| `pipe_opt` | PIPE | Optional generation data, destination overrides and images |

Either input can supply the images. When both are present, images come from `images` and metadata comes from the pipe. Output and filename values can be connected through **IO Generation Data** or **IO Context Image**, as described in [Pipe destination priority](#pipe-destination-priority).

The following settings are edited inside the panel. Inactive values remain saved in the workflow.

| Section | Setting | Default | Behavior |
| --- | --- | --- | --- |
| Mode | Save | On | Write output files; off uses temporary PNG previews |
| Mode | Preview | On | Display the results inside the node |
| Output | Custom path | On | Use Output path; off uses the ComfyUI output folder unless the pipe overrides it |
| Output | Output path | `%Y-%M-%D\%basemodel` | Relative folder or absolute destination; supports placeholders |
| Output | Custom filename | On | Use filename controls; off uses `ComfyUI_0001` unless the pipe overrides the prefix |
| Output | Filename prefix | `%basemodel, %seed, %sampler_name, %scheduler, %steps_steps` | Supports placeholders and subfolders inside the destination |
| Output | Delimiter / Counter digits / Counter first | `_` / 4 / Off | Separator, padding from 1–9 digits and counter placement |
| Format | Format | PNG | Select one of the seven formats below |
| Format | Optimize / Lossless | Off | Format-specific compression controls |
| Format | Custom quality / Quality | Off / 100 | JPG/JPEG and WebP; quality from 1–100 |
| Format | Custom DPI / DPI | Off / 300 | Print resolution from 1–2400 for supported formats; leaves pixels unchanged |
| Metadata | Embed workflow / Generation data | On | Workflow in PNG/WebP; generation parameters in PNG |
| Metadata | Remove prompts / LoRA tags / Workflow JSON | Off | Optional metadata controls described below |

---

## Placeholder System

Both `output_path` and `filename_prefix` support placeholders that are replaced with actual values at save time. Unknown or empty placeholders fall back to readable defaults.

### Available Placeholders

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `%today`, `%date` | Current date | 2025-09-27 |
| `%time` | Current time | 143052 |
| `%Y` | Year | 2025 |
| `%m`, `%M` | Month | 09 |
| `%d`, `%D` | Day | 27 |
| `%H` | Hour | 14 |
| `%S` | Second | 52 |
| `%basemodel` | Base model name | juggernaut_aftermath |
| `%model` | Full model name | juggernaut_aftermath_v5 |
| `%seed` | Generation seed | 12345 |
| `%sampler_name` | Sampler used | euler |
| `%scheduler` | Scheduler | karras |
| `%steps` | Step count | 20 |
| `%cfg` | CFG scale | 7.5 |
| `%denoise` | Denoise strength | 1.0 |
| `%clip_skip` | CLIP skip value | -2 |

### Examples

**Organized by date and model:**
```
output_path:     %Y-%M-%D/%basemodel
filename_prefix: %seed_%sampler_name_%steps
```
Result: `2025-09-27/FluxDev/12345_euler_20_0001.png`

**Simple date-based:**
```
output_path:     %today
filename_prefix: img
```
Result: `2025-09-27/img_0001.png`

---

## Output Formats

| Format | Metadata | Save Controls | Notes |
|--------|----------|-----------------|-------|
| **PNG** | Workflow + gen data | Optimization, DPI | Lossless; supports ComfyUI workflow preservation |
| **WebP** | Workflow | Quality + lossless option | Workflow/prompt in EXIF; no A1111 parameters |
| **JPG/JPEG** | None | Quality and DPI | Lossy, no workflow embedding |
| **TIFF** | None | DPI | Lossless; large files |
| **GIF** | None | N/A | Limited to 256 colors |
| **BMP** | None | DPI | Uncompressed |

---

## Metadata Embedding

### Generation data

When enabled, saved PNG files embed A1111-compatible generation data from `pipe_opt`:

- **Positive prompt** — from pipe
- **Negative prompt** — from pipe
- **Generation parameters** — steps, sampler, scheduler, CFG, seed, size, model
- **Model hash** — SHA256 short hash for CivitAI compatibility
- **LoRA hashes** — extracted from prompt, hashed for CivitAI
- **Embedding hashes** — extracted from prompt, hashed for CivitAI

The metadata follows CivitAI's expected format so images uploaded there will show full generation details.

### Workflow embedding

When enabled:
- Full ComfyUI workflow saved in PNG text chunks or WebP metadata
- Drag saved images back into ComfyUI to restore the entire workflow
- Only applies to **PNG** and **WebP** formats

### Additional Options

| Control | Effect |
|------|--------|
| Remove prompts | Strip positive/negative text from generation parameters; embedded workflows and JSON sidecars retain their original text |
| LoRA tags | Append LoRA names and weights to the prompt field in metadata |
| Workflow JSON | Save workflow as a separate `.json` file alongside the image |

---

## Preview-Only Mode

Disable **Save** in the Mode bar and keep **Preview** enabled:

- Images are saved as temporary PNG files for display, outside the configured output directory.
- Output and Format sections are hidden, with their settings retained.
- Generation-data processing and model hashing are skipped.
- Metadata offers Embed workflow so previews can still restore the workflow.
- The `files` output is empty; the input images still pass through.

---

## Pipe Integration

Connect an Eclipse-compatible PIPE output to `pipe_opt`. Save Images reads the
known values present in that context. **IO Generation Data** lets you assemble
or override the saved generation fields explicitly. When the pipe does not
contain `images` or `image`, connect decoded images to the separate `images` input.

### Keep selected images and prompts together

When several prompts produce several images, connect the selected positive and
negative text lists to **IO Generation Data**, then connect its `pipe` output to
Save Images `pipe_opt`. Save Images uses each image's corresponding pipe for
generation metadata and filename placeholders such as `%seed`.

- One pipe applies to every image, as before.
- Multiple pipes pair with image-list entries in order. Each entry can contain a
  batch, in which case its pipe applies to that whole batch.
- If the images were combined into one batch, provide one pipe per image.
- Unmatched counts raise an error rather than saving an unrelated prompt.

With **Image Selector** and **Slice & Dice**, connect the original, complete image
list or batch to Slice & Dice, and connect only the selector's `indices` output
to its `indices` input. Feed the original prompt and conditioning lists into the
matching Slice & Dice inputs. Use its selected image and text outputs downstream.
Connect the original sampler or loader PIPE list to Slice & Dice's `pipe` input
as well. Its `pipe` output follows the same selection, including multiple images
generated per sampler run. Extract the save settings from this selected output,
then combine them with the selected prompts in IO Generation Data.
Feeding the selector's already selected images into Slice & Dice applies the
original indices twice and can duplicate or reorder images.

```text
decoded images ─┬─→ Image Selector ── indices ─→ Slice & Dice
                └──────────────── image_list ─→ Slice & Dice
original positive/negative lists ─ pos_txt/neg_txt ─→ Slice & Dice
original sampler/loader pipes ───────────── pipe ─→ Slice & Dice

Slice & Dice: image_list ─→ image processing ─→ Save Images: images
Slice & Dice: pipe ─→ extract selected sampler settings ─→ IO Generation Data
Slice & Dice: pos_txt/neg_txt ─→ IO Generation Data ─→ Save Images: pipe_opt
```

Keep both branches in the same order through any later processing. Each saved
PNG contains its own generation parameters; embedded workflow data still contains
the complete workflow for reloading.

Do not mix selected prompts with an unsliced list of sampler settings. ComfyUI
maps IO Generation Data over its longest input list and repeats the last value
from shorter inputs. A larger selection can therefore hide the mismatch, while
a smaller selection produces more metadata pipes than images. Selecting the
settings alongside the images preserves both their counts and their association
when confirming a different subset or disabling later detailers.

A connected empty positive or negative prompt remains a blank string for each
selected image. This includes an empty-string branch passed through Any
Multi-Switch: IO Slice & Dice preserves the blank entries so IO Generation Data
can pair them with the selected prompts without an empty-list execution error.

### Preserve assets from multiple workflow stages

Saved generation data is not limited to the final sampling stage. Save Images
can record all models, VAEs, and LoRAs used across a multi-stage workflow when
their names are collected upstream:

1. Use a separate **Merge Strings** (`Merge Strings [Eclipse Nova]`) node for the
   model names, VAE names, and LoRA names produced by the different stages.
2. Keep `return_as_list` off and use the default `, ` delimiter.
3. Connect the three merged strings to `model_name`, `vae_name`, and
   `lora_names` on **IO Generation Data**.
4. Connect the IO Generation Data PIPE output to Save Images `pipe_opt`.

```text
stage 1 model name ─┐
stage 2 model name ─┼─→ Merge Strings ─→ IO Generation Data: model_name
stage 3 model name ─┘

repeat for VAE and LoRA names
                              IO Generation Data: pipe ─→ Save Images: pipe_opt
```

Save Images deduplicates the merged model and VAE names and processes every
entry for the saved metadata. It also deduplicates and records every merged
LoRA; LoRA strings may include weights such as `<lora:detailer:0.7>`. This keeps
the image's provenance complete instead of describing only the last stage.

The node can automatically extract metadata such as:

- Model name, VAE name, LoRA names
- Sampler settings (sampler, scheduler, steps, CFG, seed)
- Prompts (positive and negative)
- Dimensions and other generation parameters

The pipe provides values for placeholder resolution and generation metadata. Without a pipe, workflow embedding remains available, but generation parameters are not inferred from the workflow.

### Compatible Pipe Sources

| Source Node | What It Provides |
|-------------|------------------|
| **Smart Model Loader** (companion pack) | Model name, VAE name, LoRA names and enabled sampler/dimension/seed settings |
| **Smart Sampler Settings** | Sampler, scheduler, steps, CFG, denoise, seed |
| **Smart Folder** | `path` for Save Images, enabled dimensions and batch size |
| **IO Context Image** | Model info, conditioning, prompts, sampler and path/naming fields |
| **IO Generation Data** | Generation metadata and optional path/naming fields for Save Images |
| **Concat Pipe Multi** | Merged pipe from any combination of the above |

Use **Concat Pipe Multi** to combine multiple pipe sources into one before connecting to `pipe_opt` — for example, merge a Smart Model Loader pipe with a Smart Sampler Settings pipe to provide both model info and sampler settings.

---

## Outputs

| Output | Type | Description |
|--------|------|-------------|
| `images` | IMAGE | Passthrough of input images |
| `files` | STRING list | Saved file paths in image order |

---

## Usage Examples

### Basic Save with Metadata

1. Connect images to `images` and generation data to `pipe_opt`.
2. Keep Save and Preview enabled in Mode.
3. In Output, enable Custom path and Custom filename. Set Output path to `%today/%basemodel` and Filename prefix to `%seed`.
4. In Format, select PNG.
5. In Metadata, keep Embed workflow and Generation data enabled.

Connected pipe destination values take priority over the local Output settings.

### Preview Only

1. Connect images to `images`.
2. Disable Save and keep Preview enabled in Mode.
3. Images display using temporary PNGs instead of the configured output directory.

### Full Metadata with LoRA Tracking

1. Connect a generation-data pipe containing model and LoRA names to `pipe_opt`.
2. Select PNG and enable Generation data and LoRA tags under Metadata.
3. LoRA tokens are appended to the prompt metadata, with available model/LoRA hashes included.

### Minimal Output

1. Keep Save enabled and choose whether to display Preview.
2. Disable Custom path and Custom filename under Output to use the default destination and prefix, unless the pipe supplies overrides.
3. Disable Embed workflow, Generation data and Workflow JSON under Metadata.

---

## Tips & Best Practices

- **PNG and WebP** support embedded workflows for later reloads.
- **Preview-only mode** skips output naming, generation metadata and model hashing.
- **A connected pipe** supplies model names, seeds, prompts and sampler settings automatically.
- **Placeholders** such as `%today/%basemodel` keep outputs organized.
- **Quality** affects JPG/JPEG and WebP; PNG is always lossless.
- **Custom DPI** records print resolution without resizing the image.
- **Generation data** in PNG includes available model and LoRA hashes for CivitAI-compatible metadata.
