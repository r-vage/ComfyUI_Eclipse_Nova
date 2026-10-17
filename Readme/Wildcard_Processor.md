# Wildcard Processor

`Wildcard Processor [Eclipse Nova]` combines wildcard expansion, a Result
preview and both text/list outputs in the shared Nova panel design. Find it under
**🌒 Eclipse Nova → Text**. It works in standard canvas and Nodes 2.0.

This panel replaces the two former wildcard nodes.

## Panel

![Wildcard Processor Populate mode with shared Prompt and Result editors and a local seed](assets/nova-wildcard.png)

| Control | Behavior |
| --- | --- |
| Populate | Expand Prompt on each execution using the selected seed. Local edits update the Result preview. |
| Fixed | Keep the displayed Result and edit it directly. Execution uses that text without expanding wildcards or applying substitutions. |
| Local seed | Enabled: use the Seed section and ignore `seed_input`. Disabled: use the connected seed. Disabling requires a connection. |
| Prompt | Enter one prompt or several lines. Insert wildcard opens a searchable library and inserts at the text cursor. |
| Reload wildcard files | Reload the library from disk and update this node's preview. The next execution uses the reloaded library. |
| Result | Read-only preview in Populate, editable text in Fixed. Wrap changes display only. Update preview explicitly recomputes local text. |
| Seed | Exact unsigned 64-bit value, small −/+ buttons and randomize/use-last/create-fixed actions. |
| Play (▶) | Run this node and its upstream inputs once, opening Result. Available at the right of Mode even when collapsed. |

Collapse Mode or individual sections to free space within the node. Pin sections to
keep them open while opening another section. Prompt and Result share the available
node space. Their lower-right handles adjust the split without enlarging the node.
The split, section choices, wrapping and last displayed result are saved with the
workflow and retained across executions and renderer changes.

When only one text field is visible, it fills the available node space, including
Result in Fixed mode. Resizing the outer node grows or shrinks its visible fields;
reopening both restores their split. Changing sections or results keeps the chosen
node size. At small sizes, controls scroll inside the panel.

Random/increment/decrement seeds advance only after a queue submission is accepted.
The queued workflow stores the exact seed used. Previewing does not advance it;
with Randomize, the preview uses the displayed seed and a new seed is chosen when
queued. Result shows the actual execution afterward. Image Selector continuation
retains the consumed local seed.

Play uses ComfyUI's native partial execution, so connected prompts, substitutions
and seeds are resolved normally without requesting downstream nodes. Unlike
editing the local preview, Play is a real execution: participating seeds follow
their normal queue policy. Seeds on unrelated Nova nodes stay unchanged, including
a connected Seed node ignored by Local seed. ComfyUI's selected-node Run command
uses the same scoped handling.

## Connections and outputs

| Socket | Use |
| --- | --- |
| `wildcard_text` input | Overrides Prompt in Populate mode, including an empty string. |
| `substitutions` input | Accepts text or a string list of quoted assignments. All entries form one set, applied before wildcard expansion. |
| `seed_input` input | Supplies the seed when Local seed is disabled. |
| `string` output | The complete processed text, preserving spacing, blank lines and line endings. |
| `list` output | One item per non-empty line, preserving the spacing within each retained line. |

Connected values are resolved during execution. Result therefore shows the last
run for these inputs; it does not guess values from upstream widgets. Each node
has independent text, seed and preview state. Creating nodes or reloading a
workflow does not trigger preview requests; editing or explicitly refreshing
does. No canvas polling is used.

An entirely blank prompt returns an empty string and a list containing one empty
string (`[""]`). This keeps downstream mapping, including Merge Strings, working.

The entire prompt is expanded with one continuous seeded random sequence, then
split into list items. Blank lines do not restart the seed.

## Substitutions and wildcard syntax

Connect either `string` or `string_list` from **String Multiline**. Assignments
can share a line with commas:

```text
SUBJECT:"a traveler", SETTING:"{forest|coast}"
```

Or place one assignment on each line:

```text
SUBJECT:"a traveler"
SETTING:"{forest|coast}"
```

Both outputs support either layout, including a mix of commas and line breaks.
List entries are joined with line breaks into one substitution set, shared by
all connected prompts. Prompt and seed lists still process item by item, repeating
the last value of the shorter list. An empty substitution list leaves the prompt
unchanged; the combined substitutions are limited to 65,536 characters.

Use them in Prompt:

```text
{{SUBJECT}} at the {{SETTING}}
close-up of {{SUBJECT}}, __lighting__
```

Names are case-sensitive. The last assignment for a duplicate name wins.
Unknown `{{names}}` remain visible. Substitutions are applied once; wildcard syntax
inside their values is then expanded. Quoted values can include commas and line
breaks; `\"` and `\\` represent a quote and a backslash. Malformed assignments are
ignored with a warning.

File wildcards, inline choices, nested choices, weights, quantity selections and
text/YAML libraries use Eclipse's local wildcard engine. Impact Pack is not
required for wildcard processing. Nova's bundled Impact code remains in use by
Detailer/SEGS nodes.

## Syntax reference

All examples below belong in Prompt or the connected `wildcard_text` input.

| Feature | Syntax | Example result |
|---|---|---|
| Inline choice | `{red|green|blue}` | One alternative. |
| Wildcard file | `__colors__` | One line from `colors.txt`. |
| Nested path | `__people/hair-color__` | One line from `people/hair-color.txt`. |
| Weighted choice | `{3.0::portrait|1.0::illustration}` | `portrait` is three times as likely. |
| Fixed quantity | `{2$$red|green|blue}` | Two distinct alternatives, space-separated. |
| Quantity range | `{1-3$$red|green|blue}` | Between one and three distinct alternatives. |
| Custom separator | `{2$$, $$red|green|blue}` | Two alternatives separated by `, `. |
| File quantity | `{2$$__colors__}` | Two distinct entries from the file. |
| File quantifier | `3#__colors__` | Selects three entries and joins them with `|`. |
| Key pattern | `__people/*/hair__` | Selects across wildcard keys matching the pattern. |

Weighted items may also be stored directly in a wildcard file:

```text
3.0::portrait
1.0::illustration
```

The numeric prefix controls probability and is removed from the selected output.

### Nested expansion

A selected line may contain another file reference or inline choice:

```text
# subjects.txt
a {red|blue} __animals__
```

Eclipse continues resolving nested content with a depth limit so accidental cycles cannot expand forever.

### Comments

Lines beginning with `#` and empty lines are ignored in `.txt` wildcard files. In Prompt itself, comments, escapes and line endings are preserved literally.

## Wildcard files

The active library is normally:

```text
ComfyUI/models/wildcards/
```

Eclipse uses its packaged `wildcards/` directory as a fallback and as the source for examples when it creates an absent `models/wildcards` directory. An existing models directory remains user-owned.

### Text files

Use one choice per non-comment line:

```text
# ComfyUI/models/wildcards/colors.txt
amber
blue
crimson
```

Reference it as `__colors__`. Subfolders become slash-separated keys.

### YAML files

`.yaml` and `.yml` files can define nested groups:

```yaml
lighting:
  studio:
    - softbox
    - rim light
  outdoor:
    - golden hour
    - overcast daylight
```

These entries are available as `__lighting/studio__` and `__lighting/outdoor__`.

After adding or changing wildcard files, use **Reload wildcard files** in the Prompt section to update the server library and picker.

## MiniMax H3 LipSync: technical-cut directions

Put each complete camera direction on one actual line and connect `list` to
**Technical Cut Instructions** on the MiniMax H3 planner. Blank lines are skipped;
Wrap changes only the display and does not create additional list items. The
`string` output instead passes the complete multiline block as one direction.

For intentional camera cuts, choose `intentional_camera_cut` and
`original_image_reset` in the planner. FL2VA cuts require a non-zero warmup to
keep the source guide hidden. Directions cycle chronologically across eligible
technical seams. Plain text keeps its wording regardless of seed; wildcard
syntax varies the content within each direction while preserving list order.

See the [MiniMax H3 planner guide](MiniMax_H3_Audio_Planner.md#prompt-ownership)
for task prompt ownership and the complete conditioning path.

## Troubleshooting

- **A file token remains visible:** check its name in the active library and use Reload wildcard files.
- **The seed has no effect:** Fixed mode uses Result literally. In Populate, Local seed decides whether the panel or the connected input supplies the seed.
- **A connected value changed but Result did not:** press Play or queue the workflow; connected values resolve during execution.
- **You need to remove wording or tags:** connect `string` to [String Multiline](String_Multiline.md)'s `input_string`, enable **Filter**, and enter removal patterns in its editor.
