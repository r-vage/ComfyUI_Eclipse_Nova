/** Shared seed queue epochs, subgraph traversal and workflow snapshots. */
let _cachedNodeList = null;
let _hookDepth = 0;
let _queueEpoch = 0;

export function hasCurrentQueuedSeed(node, field) {
    if (node?.[field] == null) return false;
    if (_hookDepth === 0) return true;
    return node[`${field}Epoch`] === _queueEpoch;
}

// Store the resolved seed on a node so downstream consumers can read it.
export function storeQueuedSeed(node, resolved) {
    node._Eclipse_queuedSeed = resolved;
    node._Eclipse_queuedSeedEpoch = _queueEpoch;
}

// ─── Shared per-call node list ───────────────────────────────────────────────
// All Eclipse graphToPrompt hooks share one recursive walk per queue call.
// The first hook to call enterGraphToPromptHook() triggers the build;
// subsequent hooks reuse the cached list.
// exitGraphToPromptHook() clears it when the outermost hook finishes.
// Call at the entry of each graphToPrompt wrapper (before clearing seeds).
export function enterGraphToPromptHook() {
    if (_hookDepth === 0) _queueEpoch++;
    _hookDepth++;
}

// Call from a finally block after all hook post-processing is done.
// Clears the shared node list when the outermost hook finishes.
export function exitGraphToPromptHook() {
    if (--_hookDepth <= 0) {
        _hookDepth = 0;
        _cachedNodeList = null;
    }
}

// Returns the flat list of all nodes (root + all nested subgraphs) for the
// current queue call. Each entry: { node, outputKey } where outputKey is
// the colon-path string (e.g. "42:7") matching promptData.output keys.
// Built once on the first call, then cached for the duration of the call.
export function getGraphNodeList(rootGraph) {
    if (_cachedNodeList) return _cachedNodeList;
    const results = [];
    function walk(graph, prefix) {
        if (!graph?._nodes) return;
        for (const node of graph._nodes) {
            const outputKey = prefix ? `${prefix}:${node.id}` : String(node.id);
            results.push({ node, outputKey });
            if (node.subgraph) walk(node.subgraph, outputKey);
        }
    }
    walk(rootGraph, '');
    _cachedNodeList = results;
    return results;
}

// Find a node in workflow JSON data by its colon-path outputKey (e.g. "42:7").
// Handles nested subgraphs via workflow.definitions.subgraphs.
// Mirrors rgthree's get_worflow_node() server-side logic on the client side.
export function findWorkflowNode(workflow, outputKey) {
    if (!workflow) return null;
    const parts = String(outputKey).split(':');
    let nodesList = workflow.nodes || [];
    const subgraphDefs = workflow.definitions?.subgraphs || [];
    let found = null;
    for (let i = 0; i < parts.length; i++) {
        const partId = parts[i];
        found = nodesList.find(n => String(n.id) === partId) ?? null;
        if (!found) return null;
        if (i < parts.length - 1) {
            // found is a SubgraphNode wrapper — its type is the subgraph UUID/id
            const sgDef = subgraphDefs.find(sg => String(sg.id) === String(found.type));
            if (!sgDef?.nodes) return null;
            nodesList = sgDef.nodes;
        }
    }
    return found;
}
