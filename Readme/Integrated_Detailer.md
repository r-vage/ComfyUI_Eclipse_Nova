# Advanced Detailer

**Detailer (Advanced)** combines detection, region selection, mask preparation and diffusion detailing. The original **Detailer (SEGS/pipe)** remains available.

The detailer has only **image** and **pipe** inputs and outputs. Connect the original image and a PIPE containing model, VAE, positive and negative conditioning. Encode prompts upstream with your chosen text encoder; CLIP is optional in the detailer pipe.

## IO Detailer and pipe compatibility

**IO KSampler** can connect directly: both nodes use the standard `model`, `vae`, `positive`, `negative` and sampler fields. Insert **IO Detailer** to add detections or override the main settings. Its optional sockets are:

- **pipe**, to extend an existing pipe without losing other metadata.
- **model**, **clip**, **vae**, **positive**, **negative**.
- **bboxes**, **segs**, and **detection** text.
- **seed**, **sampler_name**, **scheduler**, **steps**, **cfg**, **denoise**.

Detection models, SAM2, matting, mask processing and crop controls stay in the detailer panel. There is no scheduler-function input. IO Detailer can also extract prepared SEGS and masks from the output pipe.

Connected non-None values replace inherited fields. Newly supplied boxes clear inherited SEGS; explicitly supplied SEGS take priority over boxes. A None detection preserves an inherited value. Empty detections select nothing, so that image passes through unchanged.

## Prompts for external categories

Connect Smart Detection's **SEGS** output directly to IO Detailer's **segs** input to retain category labels. Supply the same category string to Smart Detection's query and IO Detailer's **detection** input, for example `eye, mouth, breast`. Commas, semicolons and newlines separate categories; repeated names are ignored case-insensitively.

Use a String Multiline node with one positive prompt per line. Connect its **string_list** output to a text encoder, then connect the encoded output (optionally through a guidance node) to IO Detailer's **positive** input. ComfyUI encodes each prompt separately. IO Detailer preserves that conditioning list in one pipe, in the same order as the category string: first eyes, then mouth, then breasts. Detection count and sorting do not change that association. If a category has no detections, its conditioning is unused. Labels must match the category names; a mismatched list produces a clear error instead of assigning prompts to the wrong regions.

With a category conditioning list or an active category denoise list and **Combined region** enabled, external categories are combined separately: both eye masks share one sampling pass, mouth regions another, and breast masks another. Gaps between masks remain unmasked unless Fill bounding box is enabled. With Combined region disabled, instances retain separate sampling passes but use their category's prompt and denoise. SAM2 and edge refinement retain labels. Passes build on the same image so later categories preserve earlier edits.

A single positive conditioning applies to all selected regions. A multiline string stays one prompt; use **string_list** for separate entries before encoding. The detailer uses encoded tensors unchanged, including advanced encoder weighting, pooled output, guidance, masks, references and scheduled conditioning entries. It performs no internal text encoding.

The **negative** input can contain one shared conditioning or a matching category list, including the results of zeroing out the positive list. Either side can be shared; otherwise both list lengths must match. Each category receives its own positive/negative pair. The detailer runs once for the image batch and samples its selected regions without rerunning the whole node for every conditioning.

To use different denoise strengths, enter one number per line in another **String Multiline**, connect **string_list → Convert Primitive (FLOAT) → IO Detailer denoise**, and enable **Use pipe settings** on the integrated detailer. For `eye, mouth, breast`, this example applies `0.25` to both eyes, `0.40` to the mouth, and `0.30` to both breast regions:

```text
0.25
0.40
0.30
```

The denoise list follows Detection category order, even if a category has no detections or regions are sorted differently. Values must be between **0.0001 and 1**. One FLOAT applies to every category; a list must have one value per category. This works with either shared or category-specific conditionings. Turning **Use pipe settings** off uses the panel's single denoise value. The original `denoise` socket and its position are unchanged; no additional sockets are required.

Internal **YOLO uses only the first positive and negative conditioning and first denoise value**, regardless of list length. Its existing class filtering and global Combined region behavior are unchanged. Multiple external category conditionings or denoise values require SEGS because plain BBOXES contain no labels. With shared positive, negative and denoise values, Combined region retains its original behavior of combining all selected masks. IO Detailer's **positive**, **negative** and **denoise** outputs expose their lists for downstream use; the PIPE retains the standard scalar/single-conditioning form when only one is supplied.

## Detection and refinement

External **SEGS** in the pipe take priority, then external **BBOXES**. If both are absent or None, the detailer uses **YOLO**. Its model selector scans both `models/ultralytics/bbox` and `models/ultralytics/segm`, including their subfolders and registered extra paths. Entries retain their `bbox/` or `segm/` prefix so duplicate filenames can be distinguished.

The loaded checkpoint determines whether to use bounding-box detection or segmentation, regardless of its filename or folder. Detection checkpoints create rectangular masks; segmentation checkpoints retain their predicted masks. Existing BBox/Segm configurations restore the model selected in that mode. A pipe connection alone does not disable YOLO. Click **YOLO** in the Mode bar to open the detection settings.

The **SAM2** toggle optionally replaces each selected region’s mask using its bounding box. **Edges** independently enables ViTMatte, Guided filter or PyMatting. Either can be used with internal YOLO, SmartLLM boxes or supplied SEGS. Upstream detection connections are evaluated before the detailer, even when their result is None.

## YOLO detection

Choose a model, confidence threshold, overlap threshold, detection-mask dilation and context crop factor. **Detection** accepts comma-separated trained class labels or `all`. An IO Detailer detection string overrides this text. Unknown labels produce an error listing the model’s known classes; this field does not turn YOLO into a free-text detector.

**Region selection** can keep all regions or sort and take a range. The default selects the highest-confidence region in each image, matching the face-detailing flow: threshold **0.5**, dilation **10**, crop factor **2.2**, and one region starting at zero. Sorting by size or position uses the crop region, like SEGS Ordered Filter. A count of zero selects nothing.

## SmartLLM boxes and SAM2

Keep **Smart Detection → Detection to Bboxes** upstream and connect its **bboxes** output to **IO Detailer**. Feed the detailer the original image in the same order. Avoid images with rectangles already drawn on them: branch the original image before detection, or disable Smart Detection’s **Preview Boxes**. Free-text targets such as “mouth” remain in SmartLLM; SAM2 does not interpret the Detection string.

The default SAM2 model is **sam2.1_hiera_base_plus.safetensors**. **External boxes** can use all supplied boxes, the first box, or zero-based indices such as `0,2`. Coordinates are clipped to the image boundaries. Common region selection follows this preselection. For every selected box, the highest-scoring SAM2 candidate is retained. Instances stay separate unless **Combined region** is enabled.

The mask processing order is:

1. External detections or internal YOLO, followed by region selection.
2. Optional SAM2 segmentation at the source image size.
3. Optional **ViTMatte**, **Guided filter** or **PyMatting** edge refinement.
4. Black/white point adjustment when refinement is enabled.
5. Optional inversion, grow/shrink and blur.
6. Conversion to combined or separate SEGS, then diffusion detailing.

SAM2 and Edges start disabled. Edge defaults are ViTMatte, erode **3**, dilate **4**, black point **0.15**, white point **0.99** and **2 MP**. Grow and blur start at zero; instances stay separate. To reproduce the supplied LayerMask flow, enable SAM2 and Edges, select all regions, set grow/blur to **3**, enable Combined region, use crop factor **2** and minimum size **10**. ViTMatte receives the original image and a trimap derived from the selected mask. The trimap uses five erosion/dilation iterations; the finished mask returns to the source image dimensions.

The integrated adapters use the model libraries directly. LayerStyle and Impact Pack do not need to be installed. Eclipse reuses its included Impact-derived diffusion detailer and mask-to-SEGS helper. The mask preparation sequence was informed by LayerStyle’s SAM2Ultra and MaskGrow nodes; Guided filter and PyMatting are alternative refinement methods and need not produce identical edges to LayerStyle.

## Models and optional dependencies

Install the optional backends with the Python environment that runs ComfyUI:

```bash
python -m pip install -r custom_nodes/ComfyUI_Eclipse_Nova/requirements-detailer.txt
```

The file includes Ultralytics, Meta SAM2, Transformers with ViTMatte, and PyMatting. They load only when needed. Supplied SEGS/boxes with SAM2 and Edges disabled require none of these optional model backends.

Place local model files under ComfyUI’s model directory:

- `ultralytics/bbox/face_yolov8m.pt` — standard Ultralytics detection checkpoint. Other detection models in this folder appear in the selector.
- `ultralytics/segm/person_yolov8m-seg.pt` — standard Ultralytics segmentation checkpoint for Segm mode.
- `sam2/sam2.1_hiera_base_plus.safetensors` — SAM2/SAM2.1 Hiera tiny, small, base_plus or large checkpoints. Filenames must identify the architecture. FP16 safetensors variants are supported.
- `vitmatte/model.safetensors`, `vitmatte/config.json`, `vitmatte/preprocessor_config.json` — local ViTMatte files. `vitmatte-base-composition-1k` is also recognized.

Restart ComfyUI after installing dependencies or adding model files. The node does not download models automatically, substitute a different checkpoint, or enable remote model code. YOLO checkpoint loading uses a restricted architecture allowlist and PyTorch’s weights-only loader, including nested YOLO9/11/12 blocks, known training-loss state and older Dill-serialized module sets. Classification models cannot supply regions and are rejected with a specific explanation. Other unsupported checkpoints report their filename and rejected class names. A saved model that is unavailable stays visible and produces a clear execution error only when that backend is used.

**Detection device** offers **default** and **cpu**. Default follows ComfyUI’s configured accelerator and GPU index, including AMD/ROCm or DirectML when configured in ComfyUI. Older Auto/CUDA selections load as Default. CPU forces FP32; SAM2 and matting can use FP16/BF16 through PyTorch’s CUDA/ROCm backend. YOLO uses FP32. Detection and matting models are released after their pass, before diffusion detailing; there is no persistent model cache.

Official model documentation: [Meta SAM2](https://github.com/facebookresearch/sam2), [ViTMatte](https://huggingface.co/docs/transformers/model_doc/vitmatte), [Ultralytics](https://docs.ultralytics.com/).

## Sampling, outputs and batches

The Options bar, Sampler, Sizing, Mask & blending and Seed sections follow the [existing detailer](Sampler.md#detailer-segspipe). **Use pipe settings** enables sampler, scheduler, steps, CFG, denoise and seed overrides and hides the Sampler section. Missing values keep its saved local settings; turn the toggle off to edit those settings again. **Cycles** stays local and moves into Sizing while Use pipe settings is on. Models, conditioning and detection fields always come from the pipe when supplied, independently of that toggle. Supply one pipe for the complete image batch.

**Tiled encode** and **Tiled decode** start off on newly added detailers. Enable them when needed to reduce VAE memory usage. Saved workflows retain their selected values.

Completed images are available through the image and pipe outputs. The bottom sampling preview and its Preview button have been removed; existing workflows ignore their saved Preview setting. Sampling still reports progress. **Detection preview** and **Segmentation preview**, including their Stop buttons, remain available.

## Color match

Turn on **Color match** in the **Mode** bar to reveal its settings section and
bring a detailed region's colors, brightness and contrast closer to the original. It starts off,
including in existing workflows. The reference comes from the same region of
the incoming image; no additional connection is needed. Turning it off hides the
section while retaining its method and strength for the next time it is enabled.

- **Method** offers all nine methods from Image Filter Adjustments: `mkl`, `hm`,
  `reinhard`, `mvgd`, `hm-mvgd-hm`, `hm-mkl-hm`, `reinhard_lab_gpu`, `wavelet`
  and `scattersort`. The default **mkl** matches color statistics. **hm** and
  **scattersort** match tonal histograms. **reinhard_lab_gpu** matches LAB color
  statistics. **wavelet** matches low-frequency LAB tones while retaining the
  sampled crop's fine detail and spatial layout. The last three methods use
  ComfyUI's configured device, including CPU when selected.
- **Strength** ranges from **0** (no correction) to **1** (full correction),
  with intermediate values blending the color correction. It does not blend
  the original image detail back into the sampled crop.

Each region is corrected after decoding and resizing, before the normal
feathered paste. Only pixels within that region's mask supply the matching
statistics; surrounding context does not dominate the reference. Neutral
black-and-white references remain neutral at full strength. Tinted monochrome
references retain their tint. Alpha is left unchanged, and each image in a batch
uses its own original pixels.

For a detailed face that looks too bright, contrasty or tinted against the body,
start with **mkl / Strength 1** and lower the strength if needed. This corrects
tonal differences, not changes to facial structure or the placement of lighting.
Inspect the final **image** output with Image Comparer. Corrected crops also enter the output SEGS, and the
effective settings are recorded under `detailer_settings` in the pipe.

Color matching works independently of **Use pipe settings** and **Noise mask**.
It does not change detection, SAM2, matting, prompts or sampling parameters.

## Reviewing detections and masks

**Detection preview** shows the selected bounding boxes, labels and confidence before SAM2. **Segmentation preview** overlays the final prepared mask in green after SAM2, edge refinement and mask processing. Both sections can be collapsed or pinned, and their preview areas can be resized independently. Preview heights are saved with the workflow, including when their sections are collapsed. Click to cycle through a batch or double-click for the grid.

Each preview section has its own **Stop** button, disabled by default. Detection Stop pauses before segmentation; Segmentation Stop pauses before diffusion sampling. The paused section opens automatically. Queue again with unchanged images and region settings to continue. With both enabled, the first queue stops at detection, the second at segmentation, and the third samples. Changing the relevant inputs requires another review; changing only sampling settings does not invalidate the prepared regions.

Each detailer has independent reviews and completed results, including duplicated nodes with identical inputs. With several detailers, requeueing may reach the next node's enabled review stage. Leave the Stop buttons enabled: previously reviewed stages continue automatically when their inputs are unchanged.

No partial image result reaches downstream nodes while paused. The detailer's local seed advances only after completion. A bounded CPU mask cache avoids repeating preparation while reviewing, without retaining detection models, source images or ControlNet hooks. It is released after completion; if evicted, preparation is recomputed. Completed results use ComfyUI's normal cache, so changing a downstream save or display setting does not restart an unchanged detailer.

## Image and pipe outputs

Outputs are **image** and **pipe**. The pipe preserves initial generation metadata and records the effective enhancement settings under `detailer_settings`, including the category denoise list when used. It adds enhanced images, per-image SEGS and masks, and removes the stale input latent. Equal-size images form a batch inside the pipe; mixed sizes remain a list. Images and masks keep the source dimensions; the mask represents prepared regions before diffusion’s blend feather. Each image gets its own SEGS result, preserving sizes and selection order. An image with no selected regions passes through unchanged with an empty mask. BBOXES must have one group per image; boxes are never silently broadcast across unrelated images. IO Detailer’s **segs** and **mask** outputs expose those results for other nodes.

Sections can be collapsed or pinned. The node keeps its user-selected width; detection and segmentation previews retain their independently chosen heights. Both classic canvas and Nodes 2.0 use the same saved configuration.
