/** Advance folder counters and seeds only after the server accepts a submission. */
import { NODE_ID, EDITOR_KEY, clone, queueConfiguration, nextCounter } from './eclipse-smart-folder-v2-state.js';
import { nextSeed } from './eclipse-panel-seed.js';
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
        const entries = queueEntries(prompt, args[0], node => node.class_type === NODE_ID);
        if (!entries.length) return original.call(this, number, prompt, ...args);
        const snapshot = clone(prompt), updates = [];
        for (const [id, node] of entries) {
            const before = parse(node.inputs.configuration), config = queueConfiguration(node.inputs.configuration);
            const seed = config.seed ? clone(config.seed) : null;
            if (seed) config.seed.policy = 'fixed';
            if (config.folder.batch) config.folder.batch.policy = 'fixed';
            if (config.video?.vhs) config.video.vhs.skip_policy = 'fixed';
            const raw = JSON.stringify(config); snapshot.output[id].inputs.configuration = raw;
            const saved = savedNode(snapshot.workflow, id);
            if (saved) {
                saved.widgets_values = [raw]; saved.properties ??= {}; saved.properties[EDITOR_KEY] ??= {};
                if (seed) saved.properties[EDITOR_KEY].lastSeed = seed.value;
            }
            updates.push({ controller: controllers.get(liveNode(app.rootGraph ?? app.graph, id)), before, seed });
        }
        const result = await original.call(this, number, snapshot, ...args);
        if (result?.prompt_id) for (const { controller, before, seed } of updates) {
            if (!controller || controller.disposed || controller.invalid) continue;
            controller.edit(state => {
                const current = state.config;
                if (seed) {
                    if (same(current.seed, before.seed)) current.seed = nextSeed(seed);
                    state.editor.lastSeed = seed.value;
                }
                if (before.folder.batch?.policy === 'increment' && same(current.folder.batch, before.folder.batch)) {
                    current.folder.batch.number = nextCounter(before.folder.batch.number, 1n);
                }
                const vhs = before.video?.vhs;
                if (before.mode === 'video' && vhs?.skip_policy === 'increment' && before.video.context_length != null
                    && current.mode === 'video' && same(current.video?.vhs, vhs) && current.video.context_length === before.video.context_length) {
                    current.video.vhs.skip_count = nextCounter(vhs.skip_count);
                }
            });
        }
        return result;
    }
    api.queuePrompt = queuePrompt;
    return () => { if (api.queuePrompt === queuePrompt) api.queuePrompt = original; };
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const parse = raw => JSON.parse(raw);
