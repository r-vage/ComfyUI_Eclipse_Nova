# Prompt Review

**🌒 Eclipse Nova → Text → Prompt Review** displays text from an upstream node and
can hold the current run while you edit it. It accepts one prompt or a list of
prompts. Each list item stays separate and keeps its position.

**Pause is off by default.** The node displays and passes through the exact input,
including spaces and line breaks. Saved edits do not apply with Pause off.

To review before generation:

1. Put Prompt Review between the prompt source and the node that consumes its text.
2. Select **⏸ Pause** before queueing the workflow.
3. When the prompts arrive, use the dropdown or the **◀ / ▶** arrows beside it to select a prompt and edit its text.
4. Press **▶ Continue** to send all reviewed prompts downstream in the current run.

The dropdown and navigation buttons follow the selected Eclipse Nova design.

Continue does not queue the workflow again or rerun the prompt source. **Reset this
prompt** restores the selected input text. **■ Cancel run** cancels the waiting
run without returning partial prompts. ComfyUI's interrupt control also works.
The pause setting applies when the queued node executes; changing an idle node's
setting does not change an already queued request.

The editor retains its text when saving the workflow. When Pause is on, saved edits
can prefill a review only if every input prompt and its order still match. Changed
input starts a fresh review. Continue is always required again. **Refresh status**
reconnects the editor to a review still waiting in the same browser session, for
example after reloading the saved workflow. A stale review cannot continue a later
run. If the waiting editor is unavailable, use ComfyUI's interrupt control.

| Socket | Meaning |
| --- | --- |
| `prompts` input | One STRING or a STRING list from the source |
| `first_prompt` input | Optional separate opening prompt, shown first in the editor |
| `prompts` output | The incoming list, or the edited list after Continue |
| `first_prompt` output | The separate opening prompt, or an empty string if unconnected |

For **Scene Analysis to H3**, connect `first_part_prompt` to `first_prompt` and
`next_part_prompts` to `prompts`. Connect the corresponding review outputs where
those adapter outputs previously went. Leave cut times and global direction wired
as before. This reviews the opening and later scenes in one pause. A line-based
planner still needs one paragraph per list item when joining scene prompts.

A nonempty prompt cannot be erased completely during review, avoiding shifted
scene lists. The node supports up to 2,048 prompts and 1 MB of text per review.
It edits text only. Keep Pause off for unattended/API runs; interactive review
requires a ComfyUI client. While paused, this queue and its downstream generation
wait for Continue or Cancel. Already executed nodes and their loaded models are
not undone or unloaded by pausing.
