# Eclipse KSampler Advanced

A PIPE-only sampler with standard and two-stage modes. The existing Eclipse
KSampler remains available.

Connect **IO KSampler → Eclipse KSampler Advanced → IO KSampler**.
The first IO node assembles the input; the second exposes the resulting image,
latent, model, VAE, conditioning and sampling settings. IO KSampler can also update
an existing loader PIPE while preserving unrelated metadata. Connect
**IO Checkpoint Loader → IO KSampler** through their PIPE sockets. The loader’s
`model` is exposed as `model_1`; CLIP, audio VAE, model names, dimensions and other
loader fields remain in the PIPE even where IO KSampler has no separate output
socket. Use IO Checkpoint Loader to extract those loader-specific fields. Connected values
win, including zero. Supplying a new image clears an inherited latent; supplying
a new latent clears an inherited image. If both are present, sampling uses the latent.

The sampler requires model, VAE, positive and negative conditioning, and either a
latent or an image in the PIPE. An image is encoded only when no latent is present.
**Use pipe settings** uses supplied PIPE values for both stages, the seeds, optional upscale,
preview, tiled decode, tile size and Alpha. Missing values stay local. With it off,
all settings come from the panel. The switch itself is always controlled locally.

IO KSampler exposes the stage, upscale and decode settings; the master switch and optional sampling sections remain local. `preview` is a
boolean. The existing `steps`, `cfg`, `sampler_name`, `scheduler`, `denoise`
and `seed` fields control standard sampling or Stage 1. Only Stage 2 has separate
`second_*` settings; there is no duplicate Stage 1 set. On sampler output, basic
fields describe the final stage; `sampling_stages` retains the full configuration.
`second_denoise` is appended to IO KSampler's sockets, keeping existing connection
indices unchanged. Older sampler configurations default this value to 1.0.
Connecting a new base seed or offset clears an inherited
Stage 2 seed unless a new Stage 2 seed is supplied at the same time.

## Stage models and high/low-noise pairs

Connect the high-noise loader's MODEL to IO KSampler's **model_1**, and the
low-noise loader's MODEL to **model_2**. With Two-stage enabled, Stage 1 uses
model_1 and Stage 2 uses model_2 when supplied. If model_2 is absent from the
PIPE or None, Stage 2 automatically reuses model_1, including its sampling patches
and preview decoder. Standard mode ignores model_2. **Use pipe settings** does not control model
selection. Both stages share the supplied conditioning and VAE.

Before sampling, the node checks that both models use the same latent format,
channel count, downscale ratios and latent scaling. This catches incompatible
latent representations; it does not certify matching conditioning or the model
creator's intended handoff. ComfyUI manages model loading/offloading at each
sampling call. The first preview decoder is released before preparing the second.
DiT guidance is applied independently to each model when enabled; Detail Daemon
and Qwen schedules operate on whichever model/stage is active.

For a continuous high/low pass, use matching total steps and schedules, stop
Stage 1 at the model's intended switch point with **Keep leftover noise** enabled,
then start Stage 2 at that point with **Add noise** disabled. Usually leave latent
upscale off for this transition. The current Moody Moss defaults are a different
re-noising/upscale recipe and are not automatically rewritten when a second model
is connected. These two model files contain no header metadata specifying the
switch point, so follow their author's sampling settings.

IO KSampler places model_2 directly below model_1 on both sides. The primary
model uses the standard PIPE `model` field; the second uses `model_2`. Both are
preserved alongside the final image/latent. Recreate or reconnect existing IO
KSampler nodes after this socket reordering.

## Modes

- **Two-stage off:** standard sampling with the usual steps, CFG, sampler,
  scheduler and denoise controls.
- **Two-stage on:** each stage has its own total steps, sampler, scheduler, CFG,
  start/stop steps, Add noise and Keep leftover noise. Stage 1 uses denoise 1.0,
  matching ComfyUI's KSampler Advanced, and passes its latent to Stage 2.
- **Stage 2 Denoise:** when Stage 2 starts at step 0, choose its denoise strength
  just like a standard KSampler. The control uses increments of 0.01. When Start
  step is above 0, the control is disabled and ignored: denoise stays 1.0 so the
  start/stop range selects the full schedule. Its saved value is retained.
  Denoise 0 skips Stage 2 sampling; any enabled latent upscale still applies.
- **Latent upscale:** independent and on by default. When enabled in two-stage
  mode, resize between the stages using the selected method and factor. This
  option supports ordinary 4D image latents and 5D single-frame image latents,
  including Krea2 and Qwen Image. Only width and height change; the batch,
  channels and single-frame dimension are preserved. Multi-frame video and
  nested latents remain unsupported by this option.

The defaults match the configured Eclipse KSampler Advanced in the Moody Moss
workflow: Stage 1 uses 16 steps, CFG 3, er_sde/simple and range 0–12;
Stage 2 uses 25 steps, CFG 3, er_sde/beta and range 9–25. Both add noise;
only Stage 1 retains leftover noise. Bicubic latent upscale at 2× starts enabled,
and the Stage 2 seed offset is 88. Existing saved node settings remain unchanged.

The Seed section controls the base seed and an optional explicit Stage 2 seed.
When Stage 2 seed is empty, Stage 2 uses base seed + offset, wrapping
within the unsigned 64-bit range. Offset 0 reuses the base seed. An explicit Stage 2 seed takes priority over the offset. Randomization is
resolved once per queue. Image Selector confirmation freezes that base seed.

Only the final latent is decoded. Preview, tiled decode and Alpha work as in the
existing sampler. Alpha is off by default. The output PIPE contains the final
stage's settings and seed, plus `sampling_stages` describing the two-stage setup.
Changing either stage reruns the whole node; ComfyUI cannot cache Stage 1 separately.

The final preview resizes within the space below the controls. Batches open as a
grid: click a thumbnail to enlarge it, click the enlarged image to advance through
the batch, and use **Close preview** to return to the grid. This works in classic
canvas and Nodes 2.0. Live-preview decoding uses only the first image/frame and a
thumbnail-sized latent (up to 512 pixels on its longest decoded side, or a lower
configured preview size). One decoder is reused across stages when the model is unchanged. Preview-only OOMs
disable live frames for the rest of the run while preserving progress and final
image generation. This does not reduce the actual sampling or output resolution.
The advanced sampler processes the full batch together; its sampling memory still
increases with batch size and latent upscale.

## Optional sampling sections

The Options bar enables **Qwen schedule**, **DiT skip guidance** and
**Detail Daemon** independently. Each reveals a collapsible, pinnable section.
All three start off. Disabling a section retains its values. Hover a value or
button for its explanation. These three sections always use their local controls;
**Use pipe settings** does not override them and IO KSampler does not expose them.

- **Qwen schedule:** internally constructs Qwen Image 2.1 sigmas, replacing both
  scheduler dropdowns while enabled. Uses each stage's steps and actual 64-channel
  image latent dimensions, recalculating after latent upscale. Standard mode uses
  the resolved denoise fraction once. Two-stage mode uses the start/stop ranges
  and also applies Stage 2 Denoise when that stage starts at 0.
  Dynamic shifting interpolates between token-count anchors, with exponential or
  linear transformation. Fixed shift applies when dynamic shifting is disabled.
  Terminal sigma controls the final positive level before zero; 0 disables stretching.
  Training timestep units cancel in this normalized schedule, so no redundant
  training-timestep control is needed. No Smart Model Loader installation is required.
- **DiT skip guidance:** uses ComfyUI's SkipLayerGuidanceDiTSimple on a model clone
  during sampling, keeping the upstream and output PIPE models unchanged. Configure
  zero-based double/single-stream layer indices and a full-trajectory start/end
  fraction. The workflow's initial settings are single layer 22 and range 0–0.5.
  This affects the unconditional pass and normally has no effect at CFG 1. Valid
  layer indices and patch support depend on the model architecture.
- **Detail Daemon:** uses Eclipse’s built-in sampler wrapper; no extra custom node is required.
  Configure detail amount, active interval, peak position, exponent, endpoint offsets,
  fade, smoothing and optional detail CFG scaling. Each stage receives its own curve
  over its executed schedule. The defaults match the workflow (amount 0.15, range
  0.1–0.8). Only the model's sigma is adjusted; the underlying sampler retains
  its original schedule. The helper uses existing NumPy, PyTorch and ComfyUI
  dependencies, without importing plotting tools or registering extra nodes.

The Detail Daemon helper is adapted from
[Jonseed/ComfyUI-Detail-Daemon](https://github.com/Jonseed/ComfyUI-Detail-Daemon),
revision `39206d10849584e0b6ded943faca4dcd8747beb7`, under its
[MIT license](../licenses/detail-daemon-MIT.txt). Credits: muerrilla for the
concept and curve generation, blepping for the ComfyUI sampler and interpolation,
and Jonseed for the ComfyUI port.

## Moody Moss workflow settings

| Setting | Stage 1 | Stage 2 |
|---|---|---|
| Steps | 16 | 25 |
| Start / Stop | 0 / 12 | 9 / 25 |
| Sampler | er_sde | er_sde |
| Scheduler | simple | beta |
| CFG | 3 | 3 |
| Add noise | On | On |
| Keep leftover noise | On | Off |

Use a Stage 2 seed offset of **88**. Bicubic latent upscale at **2×** is enabled by default to reproduce the workflow's resolution increase; disable it to retain the input resolution. Without upscaling, both
stages operate at the input resolution. Sampler availability depends on the local
ComfyUI installation.

## Full render followed by a lower-denoise upscale pass

To reproduce **KSampler Advanced → Upscale Latent By → KSampler**, enable
Two-stage and Latent upscale, using bicubic at **1.5×** with these settings:

| Setting | Stage 1 | Stage 2 |
|---|---|---|
| Steps | 8 | 4 |
| Start / Stop | 0 / 8 | 0 / 4 |
| Sampler | er_sde | euler_ancestral |
| Scheduler | beta | beta |
| CFG | 1 | 1 |
| Denoise | 1 (internal) | 0.39 |
| Add noise | On | On |
| Keep leftover noise | Off | Off |

Use seed offset **0** if both native samplers shared the same seed. Optional
Qwen schedule, DiT guidance and Detail Daemon must be off to reproduce the
unpatched samplers. With **Use pipe settings** enabled, supplied PIPE values
take priority, so check that they match these settings too.

ComfyUI calculates `int(4 / 0.39) = 10` schedule steps and keeps the last four.
For this recipe, 4 steps with denoise 0.39 uses the same sigmas as 10 steps with
start 6 and stop 10. The new control expresses that lower-denoise pass directly.
