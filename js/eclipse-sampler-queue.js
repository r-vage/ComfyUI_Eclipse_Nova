/** Resolve seeds only on submission; accepted queues advance the editor. */
import { NODE_IDS, EDITOR_KEY, queueConfiguration, nextSeed, clone } from './eclipse-sampler-state.js';
import { queueEntries } from './eclipse-execution-scope.js';

function liveNode(graph, path) {
    let node;
    for (const id of path.split(':')) { node = graph?.getNodeById(id); graph = node?.subgraph; }
    return node;
}
function savedNode(workflow, path) {
    let nodes = workflow?.nodes, node;
    for (const id of path.split(':')) {
        node = nodes?.find(item => String(item.id) === id);
        nodes = workflow?.definitions?.subgraphs?.find(graph => graph.id === node?.type)?.nodes;
    }
    return node;
}
export function installQueueHook(api, app, controllers) {
    const original = api.queuePrompt;
    async function queuePrompt(number, prompt, ...args) {
        const entries = queueEntries(prompt, args[0], node => NODE_IDS.has(node.class_type));
        if (!entries.length) return original.call(this, number, prompt, ...args);
        const snapshot = clone(prompt), updates = [];
        for (const [id, node] of entries) {
            const before = JSON.parse(node.inputs.configuration);
            // The server knows whether a pipe contains a seed. It resolves and
            // reports the effective seed when pipe priority is selected.
            if (!before.seed || (['sampler', 'detailer', 'advanced'].includes(before.profile) && before.parameters.allow_overwrite)) continue;
            const config = queueConfiguration(node.inputs.configuration);
            const seed = clone(config.seed); config.seed.policy = 'fixed';
            const raw = JSON.stringify(config);
            snapshot.output[id].inputs.configuration = raw;
            const saved = savedNode(snapshot.workflow, id);
            if (saved) {
                saved.widgets_values = [raw]; saved.properties ??= {};
                saved.properties[EDITOR_KEY] ??= {}; saved.properties[EDITOR_KEY].lastSeed = seed.value;
            }
            updates.push({ controller: controllers.get(liveNode(app.rootGraph ?? app.graph, id)), before, seed });
        }
        const result = await original.call(this, number, snapshot, ...args);
        if (result?.prompt_id) for (const { controller, before, seed } of updates) {
            if (!controller || controller.disposed || controller.invalid) continue;
            controller.edit(state => {
                if (JSON.stringify(state.config.seed) === JSON.stringify(before.seed)
                    && state.config.parameters.allow_overwrite === before.parameters.allow_overwrite) {
                    state.config.seed = nextSeed(seed);
                }
                state.editor.lastSeed = seed.value;
            });
        }
        return result;
    }
    api.queuePrompt = queuePrompt;
    return () => { if (api.queuePrompt === queuePrompt) api.queuePrompt = original; };
}
