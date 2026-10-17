# Smart Prompt

![Smart Prompt with its folder bar, compact environment file rows and separate Seed section](assets/nova-smart-prompt.png)

**Smart Prompt [Eclipse Nova]** builds one comma-separated prompt from your text
files. It uses the same compact themed interface in classic canvas and Nodes 2.0.

## Start building a prompt

1. Add **Smart Prompt** from **Eclipse Nova → Text**.
2. Enable the folders you want in the **Folders** bar.
3. Open a folder section and choose a value for each file you want to include.
4. Press **Play (▶)** or queue the workflow. The `prompt` output contains the assembled text; the
   **Result** section shows the last executed prompt and has a Copy button.

Play sits at the right of Folders and opens Result. It runs this node and its
required upstream inputs once through ComfyUI's native partial execution, without
requesting downstream nodes. Participating seeds follow their normal queue
policy; seeds on unrelated Nova nodes stay unchanged. This also applies to
ComfyUI's selected-node Run command and nodes inside subgraphs.

| File choice | Result |
| --- | --- |
| None | Omit this file. |
| Random | Choose a line using the effective seed. |
| An exact line | Use that line until you change it. |

If a file contains the literal words `None` or `Random`, those choices appear as
`None (text)` or `Random (text)` so they remain distinct from the controls.

## Folder sections and ordering

Each folder has its own collapsible section. Collapsing it changes only the
display; the folder still contributes to the prompt. Pin a section to keep it
open when opening another section. Disable its folder button to stop using it;
its selections remain saved for when you enable it again.

Each file uses one compact row: **Filename: [choice]**, followed by the ordering
arrows and editor button. Long labels and choices shorten visually to fit the
node; hover to read the full filename or selected text.

Use the small **↑ / ↓** controls in a section header to move the folder. Its
button moves in the Folders bar too. Drag a **filename label** to reorder its row
within that folder; the jade line marks where it will land. The row arrows remain
available for single-step moves. Press **Escape** or release outside the folder
to cancel a drag.

The generated prompt follows this folder and file order. Choices stay attached
to their files when moved. Ordering supports undo and is saved per node in the
workflow, so multiple nodes can use the same library differently.

Folder names are displayed intact. Numeric prefixes are unnecessary. New folders
and files appear after saved ordering entries when you refresh. Existing choices
remain attached to their file paths. Renaming a file or folder creates a new
path; the old saved path stays visible as missing until you change your choices.

The reset icon in a section clears that folder's selections. The reset icon in
the Folders bar clears all enabled folders and keeps inactive folder drafts.
The bar itself can collapse to a compact selection summary. Reset and Play remain visible
when collapsed; expand the bar to access Refresh and Local seed.

## Seed controls

**Local seed** is the last button in the Folders bar. The Seed section is last
in the node.

| Local seed | Behavior |
| --- | --- |
| Enabled | Use the local seed; ignore `seed_input`. |
| Disabled | Use the connected `seed_input`; hide the local Seed section. |

Connect `seed_input` before disabling Local seed. Disconnecting that input
restores the local seed mode and its previous values. Input seed **0** is valid.

The local input preserves exact unsigned 64-bit values. **− / +** change the
value by one. The three moon buttons randomize each run, reuse the last queued
or executed seed, or create a fixed random seed. You can also enter `-1` for
random, `-2` for increment or `-3` for decrement. Queue acceptance advances the
seed; saving, cloning and rejected queues do not.

Random choices are deterministic for a seed and file path. Moving a row changes
prompt order without rerolling its choice. Editing a file's options can change
the random result for that file.

## Refresh and quick editing

**↻ Refresh prompt files** reloads the folder list and previously loaded or
selected files for this node. Opening a file's searchable picker also reads its
current contents. You do not need to restart ComfyUI after library edits.

When a workflow opens or the page refreshes, its loading Smart Prompt nodes share
the catalog and selected-file reads. Each distinct file is fetched once during
that load, while every node keeps its own choices and ordering. Shared results
are released when loading finishes; manual refreshes, pickers and the editor
read the current files independently.

Use the **pencil** beside a file to open the quick editor:

- Drag the editor's bottom-right corner to resize its width and height.
- Each option stays on one visual line. Long lines scroll horizontally instead
  of wrapping; resizing does not insert line breaks into the file.
- Edit one option per line and click **Save**, or press **Ctrl/Cmd+S**.
- **Cancel** closes the draft without writing it.
- **Reload file** discards the draft and reads the latest file contents.
- If someone changes the file while it is open, Save retains your draft and
  reports the conflict instead of overwriting the newer contents.

Saving changes the actual shared text file in `prompts/`. The current node's
choices update immediately. Other open nodes can refresh their own lists;
execution always checks the current file contents.

A removed file or selected line stays visible as **missing/unavailable**. It is
never silently changed to None. Choose another line, select None, or disable
the folder before executing. Newly discovered files start at None.

## Your prompt library

Create UTF-8 `.txt` files beneath folders in this repository's `prompts/`:

```text
prompts/
├── subjects/
│   ├── Character.txt
│   └── Pose.txt
├── settings/
│   └── Lighting.txt
└── My collection/
    └── Locations/
        └── Scene.txt
```

Nested folders with text files appear using their relative path, such as
`My collection/Locations`. Both numbered and unnumbered filenames work. Names,
including spaces, digits and underscores, are retained; `.txt` is omitted from
the row label. Blank lines are ignored. Repeated lines still weight Random
selection. Each file can contain up to 1 MiB of text.

Bundled filenames use plain names such as `Character.txt` and `Hair Colors.txt`,
without ordering numbers, underscores or a `_desc` suffix. Description variants
remain in their own folders, so matching filenames are distinct files. Use the
row arrows or drag the filename labels to choose the order instead of adding
numbers to filenames.

Hidden folders/files, symbolic links and the internal `tag_lists` library are
excluded. The editor can modify existing prompt text files; create or rename
files and folders through your file manager, then refresh the node.

The **Result** section reflects the last execution, not a live recomputation
while editing. Press Play or requeue after changing choices or file contents to update it.
