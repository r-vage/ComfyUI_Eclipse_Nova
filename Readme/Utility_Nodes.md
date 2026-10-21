# Utility Nodes Guide

Quick reference for Eclipse's helper nodes — routers, joiners, cleanup, and other small utilities that glue workflows together.

## Table of Contents
- [Utility Nodes Guide](#utility-nodes-guide)
  - [Table of Contents](#table-of-contents)
  - [Routers](#routers)
    - [Any Multi-Switch](#any-multi-switch)
    - [Any Multi-Switch Mixed](#any-multi-switch-mixed)
    - [Any Multi-Switch Purge](#any-multi-switch-purge)
    - [Any Dual-Switch](#any-dual-switch)
    - [IF A Else B](#if-a-else-b)
    - [IF A Else B (Fallback)](#if-a-else-b-fallback)
    - [Any Passer / Passer Purge](#any-passer--passer-purge)
  - [Conversion \& Joining](#conversion--joining)
    - [Join](#join)
    - [Concat Pipe Multi](#concat-pipe-multi)
  - [Text](#text)
    - [String DeDuplicate](#string-deduplicate)
  - [Tools](#tools)
    - [Seed](#seed)
    - [Show Any](#show-any)
    - [Stop](#stop)
    - [Resolution Scale](#resolution-scale)
    - [Mode Control Tools](#mode-control-tools)
    - [Loop Calculator / Keep Calculator](#loop-calculator--keep-calculator)

---

## Routers

Routing nodes live in `Eclipse Nova > Router`. They accept **any type** — models, images, latents, strings, pipes — and forward based on conditions.

### Any Multi-Switch

The workhorse of fallback chains. Accepts up to 64 inputs and returns the **first non-None** value. Input slots **auto-grow** — connect to the last slot and a new one appears. Disconnect trailing empty slots and they shrink. The `inputcount` widget is hidden.

| Input | Type | Description |
|-------|------|-------------|
| `any_1`–`any_N` | Any (optional) | Inputs checked in order, highest priority first |

**Output:** Single `Any` — the first input that is not None, not empty string, not empty dict/tuple/list.

**Key behavior:**
- Inputs are checked top to bottom — `any_1` has highest priority
- None, `""`, empty containers are all skipped
- If all inputs were empty strings, returns `""` (not None) — preserves string type
- If all inputs are None, returns None

**Common pattern:** Pair with [Get All Active](GetFirst_GetAllActive.md) to build progressive pipelines where the Multi-Switch picks the latest active result.

### Any Multi-Switch Mixed

Accepts different types at the same time, for example VIDEO in `any_1` and IMAGE
in `any_2`. Returns the first nonempty input from top to bottom, unchanged.
Mute the higher-priority source to use the next available input. Slots grow
automatically up to 64; no selector widget is needed.

The output is a wildcard. Connect it to a destination that supports every type
your branches may produce, such as **Save Video Data [Eclipse Nova]** for IMAGE/VIDEO.
The switch does not convert types. All connected, active branches execute
normally. Empty strings/containers and None are skipped; zero and False are
valid values. If every input is empty, the output is None. Image batches and
ComfyUI lists retain their original objects and list structure.

INT, FLOAT, STRING and BOOLEAN values can share this switch, and its output can
connect to a destination socket that accepts several types. Selection depends
on input priority and availability, not on the destination: an incompatible
selected value is not automatically replaced with a lower-priority input.

ComfyUI's built-in **Math Expression** (`ComfyMathExpression`) currently declares
FLOAT, INT and BOOLEAN inputs. These work directly through the switch. Numeric
strings remain strings; use an explicit expression such as `float(a) * 2` to
convert one. Arbitrary text cannot be used as a number.

Wildcard connections pass ComfyUI's static type validation. The destination
handles the actual value during execution: Math Expression reports an error for
an invalid conversion or a nonnumeric result. Other nodes may validate, convert
or reject values differently; a type-mismatch warning before queueing is not
guaranteed.

For caption muting, see [the lyric-caption wiring](Lyric_Captions.md#muting-captions).

### Any Multi-Switch Purge

Same as Any Multi-Switch but with an added `Purge_VRAM` toggle. When enabled, purges VRAM before returning the result. Useful when switching between model-heavy branches where you want to free the unused model's VRAM.

### Any Dual-Switch

Manual 1-of-2 selector. Set `Input` to 1 or 2 to choose which input passes through.

| Input | Type | Description |
|-------|------|-------------|
| `Input` | Int (1–2) | Which input to output |
| `input1` | Any (optional) | First option |
| `input2` | Any (optional) | Second option |

Also available as **Any Dual-Switch Purge** with VRAM cleanup.

### IF A Else B

Boolean-controlled router. Unlike Dual-Switch which uses an integer selector, this takes a boolean condition.

| Input | Type | Description |
|-------|------|-------------|
| `on_true` | Any | Value returned when boolean is True |
| `on_false` | Any | Value returned when boolean is False |
| `boolean` | Boolean (force_input) | The condition — must be wired from another node |
| `Purge_VRAM` | Boolean | Optional VRAM cleanup before switching |

### IF A Else B (Fallback)

Same as IF A Else B but with a safe default: the `boolean` input is **optional**. When unconnected or from a muted node, it defaults to False (on_false path). The `on_false` input is also optional — returns None if unconnected.

This is useful when the condition comes from an optional group that may be muted.

### Any Passer / Passer Purge

Passthrough nodes — input goes straight to output unchanged. Seems pointless, but useful for:
- **Execution ordering** — forces ComfyUI to execute the source before downstream nodes
- **VRAM Purge variant** — clears VRAM at a specific point in the pipeline without adding logic

---

## Conversion & Joining

### Join

Combines multiple inputs into one. Auto-detects the input type and handles each differently. Input slots **auto-grow** — the `inputcount` widget is hidden.

| Input | Type | Description |
|-------|------|-------------|
| `delimiter` | String | Separator for string joins (default: `", "`, use `\n` for newline) |
| `input_1`–`input_N` | Any (optional) | Values to join |

**Type-specific behavior:**

| Input Type | Join Method |
|-----------|-------------|
| **STRING** | Concatenated with delimiter |
| **IMAGE** | Tensors resized to match first image, then batched (cat along dim 0) |
| **MASK** | Tensors batched (cat along dim 0) |
| **AUDIO** | Clips appended in input order along the timeline; differing sample rates are resampled to the highest rate and mono is expanded when needed |
| **INT / FLOAT** | Converted to strings and joined with delimiter |
| **LIST** | Flattened and joined with delimiter |

For consecutive video segments, join their audio outputs here before connecting the
single result to Save Video with Generation Data. ComfyUI's **Merge Audio** overlays tracks from time
zero; use it for simultaneous layers, not for sequential video segments.

**Category:** `Eclipse Nova > Conversion`

### Concat Pipe Multi

Merges 2–64 pipe/context dicts into a single pipe. Essential when combining outputs from multiple groups that each produce partial pipes. Input slots **auto-grow** — the `inputcount` widget is hidden.

| Input | Type | Description |
|-------|------|-------------|
| `pipe_1`–`pipe_N` | PIPE (optional) | Pipe inputs, processed in order |
| `merge_strategy` | Combo | How to handle key conflicts |

**Merge strategies:**

| Strategy | Behavior |
|----------|----------|
| `overwrite` | Later pipes replace earlier values for the same key |
| `preserve` | First valid (non-None) value wins — later pipes can't overwrite |
| `merge` | Combines lists, uses later values for scalar conflicts |

**Output:** Single `PIPE` — merged context dict.

Every non-empty dictionary field is accepted, including custom fields, `model_2`,
Stage 2 controls and `sampling_stages`; there is no fixed field whitelist. Zero
and False are valid values. Nested audio, latent and configuration dictionaries
stay intact, with conflict resolution applied to the whole field. Structured
`loras` entries remain separate from the `lora_names` text field.

To combine loader metadata with actual sampling results, use **overwrite**:
loader PIPE first, sampler output PIPE last. This keeps model names while using
the resolved seed/settings/dimensions. **Merge** intentionally concatenates images
and lists, so combining a PIPE with its sampled output can duplicate images.
An existing IO KSampler already preserves unrelated loader fields; a separate
Concat node is unnecessary for that direct connection.

See the "Connecting the Pipe" sections in [Smart Model Loader Nova](https://github.com/r-vage/ComfyUI_SmartModelLoader_Nova), [Sampler Settings](Sampler.md#smart-sampler-settings), and [Smart Folder](Smart_Folder.md) for usage examples.

**Category:** `Eclipse Nova > Conversion`

---

## Text

### String DeDuplicate

Combines multiple string inputs and removes duplicate entries. Handles both tag format (comma-separated) and prose (line-based). Input slots **auto-grow** (up to 20) — the `inputcount` widget is hidden.

| Input | Type | Description |
|-------|------|-------------|
| `dedup_inputs` | Boolean | Also deduplicate within each input before combining |
| `weight_handling` | Combo | `None`, `Remove Weights`, or `Normalize` (caps at 1.4) |
| `string_1`–`string_N` | String (force_input) | Text inputs to merge |

**Key behavior:**
- Auto-detects tag format vs prose
- Case-insensitive deduplication (underscores normalized to spaces)
- Expands weighted groups like `((a:2, b))` before dedup
- `Remove Weights` strips all emphasis markers (`(( ))`, `:1.5`, etc.)
- `Normalize` caps weight values at 1.4 to prevent overemphasis
- Empty inputs are silently ignored

**Category:** `Eclipse Nova > Text`

---

## Tools

### Seed

**Seed [Eclipse Nova]** has no input sockets and one `SEED` integer output. Its
compact panel uses the selected Nova design in standard canvas and Nodes 2.0.

- **64-bit** is enabled by default. Disable it for unsigned 32-bit values;
  switching down keeps the lower 32 bits of the current value.
- The seed row provides **− / +**, **randomize each run**, **use last queued seed**,
  and **create fixed random seed**. The field also accepts `-1` for random,
  `-2` for increment, or `-3` for decrement. Automatic changes advance only after
  the queue accepts the prompt. Exact values are retained up to `18446744073709551615`.
- **Results**, collapsed initially, keeps the 20 most recently used distinct
  seeds, newest first. Click a seed to reuse it; a larger seed also enables
  64-bit mode. The reset icon clears this list. History is saved per node in the
  workflow and fills when the node executes through a connected output branch.

Saved generation workflows contain the resolved fixed seed. Connected wildcard
processors share that value, and Image Selector retains it when continuing a
selection. Reopening Results or clearing history does not change the output seed.

### Show Any

Displays any input as readable text in the node. Strings, numbers, tensors, dictionaries, and lists are supported.

| Input | Type | Description |
|-------|------|-------------|
| `anything` | Any (optional) | Value to inspect |

**Output:** Passes the input through unchanged — can be inserted anywhere without breaking the chain.

**[Show Any Stop](DOM_Previews.md)** adds a resizable text panel and a **Stop** button in its **Mode** bar, disabled by default. Enable it to interrupt after displaying the value for review. Queue unchanged inputs again to continue through the cached result.

**Category:** `Eclipse Nova > Tools`

### Stop

Halts workflow execution at this point. Connect it inline to create a breakpoint — everything before it executes, everything after it doesn't.

| Input | Type | Description |
|-------|------|-------------|
| `input` | Any | Value to pass through before stopping |

**Output:** The input value (downstream nodes won't execute due to interrupt).

**Tip:** Bypass the Stop node (mode 4) to let execution continue past it. Useful as a toggleable checkpoint.

**Category:** `Eclipse Nova > Tools`

### Resolution Scale

Scales image resolutions and coordinate boundaries (e.g. for crop and detailer offsets) based on scale multipliers.

| Input | Type | Description |
|-------|------|-------------|
| `width` | Int | Target width |
| `height` | Int | Target height |
| `scale` | Float | Multiplier ratio |

**Category:** `Eclipse Nova > Tools`

### Mode Control Tools

A suite of nodes (`Mode Toggle`, `Switcher`, `Repeater`, `Relay`, and `Bridge Set/Get`) designed to wireless control execution flows, muting/bypassing entire subgraphs, or routing wireless named data channels across your workflow canvas.

**Category:** `Eclipse Nova > Tools`

### Loop Calculator / Keep Calculator

Video processing helpers for calculating loop iterations and frame counts:

**Loop Calculator** — Given total frames, context length, and overlap, calculates how many loops are needed to process the entire video.

**Keep Calculator** — Given the same parameters plus the current loop count, calculates how many frames to keep from the current batch.

Both are used with video pipelines (e.g., SeedVR2, AnimateDiff) to handle frame batching correctly.

**Category:** `Eclipse Nova > Tools`
