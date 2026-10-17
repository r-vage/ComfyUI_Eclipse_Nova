# Danbooru Prompt Forge

Danbooru Prompt Forge selects one taglist from a locally stored offline corpus, then
turns it into a filtered prompt. It is useful for producing seed-repeatable scene
and composition ideas for models that understand Danbooru-style tags.

The node is in `🌒 Eclipse Nova/ Danbooru`. It is an output node, so it can be queued
directly even when none of its outputs are connected.

**Danbooru Prompt Forge** provides a Mode bar, pinnable text sections and
local/input seed controls in the shared panel design. See the
[Prompt Forge panel guide](Prompt_Forge_Panel.md) for the controls; this guide
also covers the local corpus files and custom categories.

## Visual tour

![Prompt Forge with local corpus controls and separate text sections](assets/nova-prompt-forge.png)

### Assemble a repeatable prompt

Use **Prefix** and **Custom prompt** for explicit tags, constrain the candidate
pool with **Required tags**, and fix the seed when the same local corpus
selection should be reproduced later. Pin text sections to keep them open together.

### Make filtering policy visible

Open **Mode** to choose rating pools, final underscore formatting,
missing-required-tag behavior, and category filtering. Enabling **Categories**
reveals the **Category exclusions** section.

The panel stores selections, text and seeds in one configuration widget. They
are preserved when switching between Nodes 2.0 and the standard canvas,
including saved workflows.

## Selection and filtering

1. The **Mode** bar chooses which content-rating pools participate:
   **General**, **Questionable**, **Sensitive**, and **Explicit**. It also contains
   **Underscores** for output formatting and **Ignore missing** for forgiving
   required-tag matching. **Categories** enables generated-tag filtering.
   New nodes select General, Underscores and Local seed, so Prompt Forge initially
   runs directly from the rating corpus without requiring categorization.
2. **Prefix** adds explicit tags at the beginning of the assembled prompt. It does
   not constrain taglist selection.
3. **Required tags** keeps only candidates containing every listed tag. By
   default, an unavailable required tag produces a no-matches error. With
   `ignore_missing` selected, required tags absent from every enabled pool are
   ignored, the remaining found tags still constrain selection, and the console
   reports which tags were ignored.
4. `seed` deterministically shuffles the remaining candidates and selects one.
   The same corpus, settings, and seed produce the same result.
5. Every selected rating line begins with `post_id, score`; Prompt Forge always
   removes those two metadata fields. With `categories` enabled, tags absent from
   `categorized_tags.txt` are removed from the generated segment, then
   `exclude_tag_categories` removes generated tags assigned to excluded
   categories. With `categories` off, generated tags pass through in their rating
   file order and the category files are not required.
6. `custom_prompt` adds explicit tags after the required tags and before the
   generated segment. The four segments are deduplicated together while keeping
   each tag's first occurrence.

`prefix`, required tags, and `custom_prompt` accept comma- or newline-separated
values. Spaces inside a tag are normalized to underscores, so `white shirt` and
`white_shirt` are equivalent. Explicit prefix, required, and custom tags bypass
category exclusion. When `categories` is enabled, category filtering applies only
to the generated corpus segment; category names are validated, and an
invalid-category error lists the accepted names. When it is disabled, the saved
exclusion value is ignored. For final tag or phrase removal, connect the output to
[String Multiline](String_Multiline.md)'s `input_string`, enable **Filter**, and
enter removal patterns in its editor. The **Underscores** switch
changes underscores to spaces across the complete assembled prompt after
filtering and deduplication.

`ignore_missing` does not replace rating-pool selection and does not relax a set
of found tags that cannot coexist in one candidate. Those cases still produce the
no-matches error. A missing required tag ignored for candidate selection remains
at the start of the final prompt because it was explicitly supplied.

Content-rating controls select source pools; they are not a classifier or a
guarantee about every individual tag. Downloaded or self-created questionable,
sensitive, and explicit pools may produce sexual or otherwise mature content.

## Seed controls

The **Seed** section sits below the text sections and uses the shared panel
controls, including small minus/plus buttons for exact 64-bit values:

- `🌑 Randomize Each Time` keeps the visible seed in random mode and resolves a
  new concrete seed whenever the workflow is queued.
- `🌕 New Fixed Random` generates a concrete seed immediately, so later queues
  reuse it until you change it.
- `🌘 (Use Last Queued Seed)` becomes available after a queue and
  restores the concrete seed used for that queue.

**Local seed** uses the panel value even when `seed_input` is connected. Disable
it in Mode to use the incoming seed and hide the local controls. Without a
connection it stays enabled; disconnecting the input restores local mode.
Queued workflows retain the concrete seed, and random/increment/decrement
policies advance only after queue acceptance. Saving does not advance the seed.

## Outputs

- `text`: prefix tags, required tags, custom tags, and generated tags in that
  order, globally deduplicated by first occurrence. With `categories` enabled,
  generated tags use the local category-index order; otherwise they retain the
  selected rating line's order.

## Corpus setup and provenance

Eclipse ships ready-to-use snapshots of the categorized index and the general,
sensitive, questionable, and explicit rating corpora. On a fresh install,
startup extracts these packaged `.example` defaults into `prompts/tag_lists/`.
On updates, hash-aware extraction refreshes an unchanged runtime file while
preserving any file the user has modified or intentionally deleted. The files
use these exact names:

- `taglists-general.txt`
- `taglists-questionable.txt`
- `taglists-sensitive.txt`
- `taglists-explicit.txt`

Replace the rating files with compatible files from your own tools or the
[`rainlizard/ComfyUI-Raffle` lists directory](https://github.com/rainlizard/ComfyUI-Raffle/tree/main/lists).
Each nonempty line uses `post_id, score, tag, tag, ...`. Prompt Forge reads these
files at execution; changing them can change the prompt selected by a given seed.

The distributed category index, categorized-tag snapshot, and rating corpora are
adapted from the
[`rainlizard/ComfyUI-Raffle`](https://github.com/rainlizard/ComfyUI-Raffle)
dataset; redistribution and adaptation were confirmed with permission.

The Prompt Forge node itself performs no network requests. Its corpus lives in the
data-only `prompts/tag_lists/` directory. Smart Prompt and
Eclipse's wildcard loader exclude this directory from prompt discovery. The
distributed default files are:

- `categories.txt`
- `categorized_tags.txt`
- `taglists-general.txt`
- `taglists-sensitive.txt`
- `taglists-questionable.txt`
- `taglists-explicit.txt`

## Custom categories

Add a lowercase category name on its own line in `prompts/tag_lists/categories.txt`,
then assign tags to it in `categorized_tags.txt`:

```text
[vehicles_and_machinery] airplane
[vehicles_and_machinery] construction_vehicle
[vehicles_and_machinery] motorcycle
```

Enable **Categories** in Prompt Forge to use the index. Category exclusions apply
to generated tags; explicit Prefix, Required tags and Custom prompt tags remain.
Keep local edits in `prompts/tag_lists/`; packaged defaults are installation data.
Existing user corpora and any external categorization files are retained.
