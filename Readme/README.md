# Eclipse Nova documentation

Start with the **[visual tour](Visual_Tour.md)** for the current panels, or pick a
guide below. Screenshots use real ComfyUI nodes with the Amber theme. The same
panels work in classic canvas and Nodes 2.0; Neutral is the default design.

See the [main README](../README.md) for installation, pack boundaries and data
folders. Nova nodes use `[Eclipse Nova]` IDs and the **🌒 Eclipse Nova** menu.

## Appearance and panel controls

| Guide | What it covers |
| --- | --- |
| [Node designs](Node_Design.md) | Neutral and colored palettes, including Neutral color variants; custom JSON themes, reload and saved background behavior |
| [Operation panels](Operation_Panels.md) | Compact image-batch, tile, timing, text and folder tools; connected value overrides |
| [Previews and Stop](DOM_Previews.md) | Show Any Stop, image/mask previews, resizable output and continuation when reviewed inputs are unchanged |
| [Media tools](Media_Tool_Panels.md) | Image Convert, Crop by Mask and System Audio Recorder panels |

## Prompts and text

| Guide | What it covers |
| --- | --- |
| [Smart Prompt](Smart_Prompt.md) | Editable folder/file lists, searchable choices, drag ordering, refresh and local/input seeds |
| [Seed and Dual Seed](Seed.md) | Exact Image/Prompt seed controls, shared 32/64-bit range and 50-entry result histories |
| [Wildcard Processor](Wildcard_Processor.md) | Populate/Fixed modes, Prompt/Result/Seed sections, substitutions and string/list outputs |
| [String Multiline](String_Multiline.md) | Text or filtering patterns, preview, Stop, prefix input and per-line list output |
| [Prompt Styler](Prompt_Styler.md) | Style libraries, positive/negative controls, underscore removal and queue-aware index actions |
| [Prompt Forge panel](Prompt_Forge_Panel.md) | Mode bar, pinnable text sections, generation controls and seed overrides |
| [Prompt Forge corpus](Danbooru_Prompt_Forge.md) | Local tag lists, category/rating pools and offline corpus preparation |
| [Read Prompt Files](ReadPromptFiles.md) | File lists, fixed/random/next/previous/shuffle selection, last-index status and seed freezing |
| [Save Prompt](Save_Prompt.md) | TXT/CSV/JSON, caption pairing, output placeholders and write modes |

Wildcard Processor, String Multiline and Prompt Forge keep their visible text
editors inside the node’s chosen bounds. Open editors share the space; collapsing
a section gives the remaining editors more room. **Play** runs the graph up to
that node. Where **Stop** is offered, it is an independent review checkpoint for
regular queues.

## Sampling, size and folders

| Guide | What it covers |
| --- | --- |
| [Advanced sampler](Advanced_Sampler.md) | PIPE-only standard/two-stage sampling and IO KSampler; optional latent upscale |
| [Sampler panels](Sampler.md) | Smart Sampler Settings, Eclipse KSampler and Detailer; pipe priority, seed controls and previews |
| [Smart Folder](Smart_Folder.md) | Output paths, image/video size, video timing and a separate Seed section |
| [Resolution Pipe](Resolution_Pipe.md) | Aspect/resolution menus, custom dimensions, divisibility and optional batch size |

## Images and saving

| Guide | What it covers |
| --- | --- |
| [Image loaders](Image_Loaders.md) | Load Image grid/upload/metadata and Load Files From Folder Single/Range/Step modes |
| [Image Resize](Image_Resize.md) | Mode-specific controls, padding color and optional width/height priority |
| [Image adjustments](Image_Adjustments.md) | Softening, upscale, reference color match, color/detail/grade, sharpening and finish effects |
| [Text and Image FX](Image_FX.md) | Typography, compositing, effects and color pickers |
| [Selection and comparison](Image_Review.md) | Ordered Image Selector review and Image Comparer Slide/Click modes |
| [Batch selection and slicing](Batch_Selection_Slice_Dice.md) | Keep images, filenames and other list data aligned through curation |
| [Image Review Filter](Image_Review_Filter.md) | Split aligned review reports into kept and rejected images |
| [Save Images](Save_Images.md) | Format/metadata controls, custom DPI, pipe destination priority and resizable previews |

Load Image’s **Generation settings** section lets you choose which available
sampler values, prompts and seed enter its pipe. It does not load models from
image metadata.

## Audio and video

| Guide | What it covers |
| --- | --- |
| [Load Audio](Load_Audio.md) | File or connected audio, auditioning, trim inputs and optional review |
| [System Audio Recorder](System_Audio_Recorder.md) | Manual system-output capture, silence trim, WAV/MP3 and retained-source updates |
| [Load / Preview / Split Video](Load_Video.md) | Editable clip slots beside the preview, per-clip trims, input overrides and timing-preserving extraction |
| [Image Timeline Video](Image_Timeline_Video.md) | PIPE renderer and IO, manual image slots or Image Selector, per-image crop/blending and selected metadata, even/quiet-gap/manual timing for captions or saving |
| [Upscale Video](Upscale_Video.md) | Integrated model selection, bounded frame batches, source timing and audio |
| [Save Video with Generation Data](Save_Video_Data.md) | IMAGE/VIDEO/timeline saving, output and encoding controls, trim/loop behavior and metadata |
| [Lyric Captions](Lyric_Captions.md) | PIPE renderer and IO slots, shared transcription, optional wording/timing corrections and caption controls |
| [Frame timelines](Frame_Timeline.md) | Disk-backed append/trim, preview/export and base-only loop plans |
| [MiniMax H3 planning](MiniMax_H3_Audio_Planner.md) | Three segmented-planning panels under **Eclipse Nova → MiniMax** |

## Character workflows

All character tools are under **Eclipse Nova → Character**.

| Guide | What it covers |
| --- | --- |
| [Character references and sheets](Character_Reference_Nodes.md) | Prepare/Select/Pack roles, sheet assembly, manual/automatic crops and reports |
| [Character Shot Planner](Character_Shot_Planner.md) | Planner sections, connected overrides, persistent reservations, replay and aligned prompt/seed lists |

## Routing, pipes and utilities

| Guide | What it covers |
| --- | --- |
| [Set/Get and Mode Bridge](Set_Get_Bridge.md) | Named channels, subgraph scope and wireless mute/bypass control |
| [Get First / Get All Active](GetFirst_GetAllActive.md) | Priority routing, shared chains, per-member choices and positional output wiring |
| [Utilities](Utility_Nodes.md) | Switches, joiners, pipe merging, cleanup, string helpers and timing utilities |

Routing, primitive and dynamic-input nodes keep the controls their workflows
need. The panel redesign does not require them to adopt a configuration editor.
See [Pipes and connected overrides](../README.md#pipes-and-connected-overrides)
for the distinction between `PIPE`, `BASIC_PIPE` and explicit input values.

## Companion packs

- [Smart Model Loader Nova](https://github.com/r-vage/ComfyUI_SmartModelLoader_Nova)
  owns diffusion loaders, CLIP/LoRA tools, presets, model source/integrity and the
  Download Manager. Use that repository’s guides for model acquisition and
  Nunchaku setup.
- [SmartLLM Nova](https://github.com/r-vage/ComfyUI_SmartLLM_Nova) owns language-model and
  detection tooling. Follow the setup guide for the edition used by your workflow.

Each pack has independent settings and private configuration. Installing Nova
does not provide the original Eclipse node IDs or install its companions.

## Quick answers

**Change the colors:** open **Settings → Eclipse Nova → Appearance → Node design**.
A selected theme styles controls and untouched node defaults. Saved custom titles
and backgrounds remain, including on Float and routing nodes.
See [Node designs](Node_Design.md).

**Edit prompt/style files:** use this pack’s `prompts/`, `styles/`, `wildcards/`
and `patterns/` folders. Refresh the relevant node after editing. User-modified
and intentionally deleted known defaults are preserved on startup.

**Missing models or downloads:** use
[Smart Model Loader Nova](https://github.com/r-vage/ComfyUI_SmartModelLoader_Nova).
Those controls are not part of Eclipse Nova.

**Report an issue:** include the renderer, ComfyUI/frontend versions and a small
reproduction in [GitHub Issues](https://github.com/r-vage/ComfyUI_Eclipse_Nova/issues).
See the [main README](../README.md) for installation and troubleshooting.
