/** Submission-time dependency scope shared by Nova's queue hooks. */
const localSeedInputs = new Map();

// Match the seed_input removal performed by the panel hook, regardless of
// extension installation order. A locally ignored seed is not a dependency.
export function registerLocalSeedInput(nodeId, usesSeed) {
    const previous = localSeedInputs.get(nodeId);
    localSeedInputs.set(nodeId, usesSeed);
    return () => {
        if (localSeedInputs.get(nodeId) !== usesSeed) return;
        if (previous) localSeedInputs.set(nodeId, previous);
        else localSeedInputs.delete(nodeId);
    };
}

export function executionScope(prompt, options) {
    const targets = options?.partialExecutionTargets;
    if (!Array.isArray(targets)) return null; // Full queues retain their existing behavior.
    const output = prompt?.output ?? {}, selected = new Set(), pending = targets.map(String);
    while (pending.length) {
        const id = pending.pop(), node = output[id];
        if (!node || selected.has(id)) continue;
        selected.add(id);
        let localSeed = false;
        const usesSeed = localSeedInputs.get(node.class_type);
        if (usesSeed) {
            try {
                const config = JSON.parse(node.inputs?.configuration);
                localSeed = config.seed?.source === 'local' && usesSeed(config);
            } catch { /* Let ComfyUI report invalid configurations on the requested branch. */ }
        }
        for (const [name, value] of Object.entries(node.inputs ?? {})) {
            if (name === 'seed_input' && localSeed) continue;
            if (Array.isArray(value) && value.length === 2 && typeof value[0] === 'string'
                && Number.isInteger(value[1]) && value[1] >= 0 && Object.hasOwn(output, value[0])) pending.push(value[0]);
        }
    }
    return selected;
}

export function queueEntries(prompt, options, accepts) {
    const scope = executionScope(prompt, options);
    return Object.entries(prompt?.output ?? {}).filter(([id, node]) => (!scope || scope.has(id)) && accepts(node));
}

// Match native selected-node execution's root-to-subgraph instance path.
// Resolve only on a click, without changing selection or watching the canvas.
export function executionTarget(rootGraph, node, { requireEnabled = true } = {}) {
    // Retained recorder sessions also need their owner path while muted. Run
    // actions keep the default enabled-node and enabled-ancestor checks.
    if (!node?.graph || (requireEnabled && [2, 4].includes(node.mode))) throw Error('Enable this node before running it.');
    const parents = new Set();
    function find(graph, prefix) {
        if (!graph || parents.has(graph)) return null;
        parents.add(graph);
        try {
            for (const candidate of graph._nodes ?? []) {
                if (requireEnabled && [2, 4].includes(candidate.mode)) continue;
                const path = prefix ? `${prefix}:${candidate.id}` : String(candidate.id);
                if (candidate === node) return path;
                if (candidate.subgraph) {
                    const nested = find(candidate.subgraph, path);
                    if (nested) return nested;
                }
            }
            return null;
        } finally { parents.delete(graph); }
    }
    const id = find(rootGraph, '');
    if (!id) throw Error('This node is not in the active workflow, or its subgraph is disabled.');
    return id;
}
