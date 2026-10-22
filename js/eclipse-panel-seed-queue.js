/** Resolve local/input seeds for structured panels only on queue submission. */
import { nextSeed, randomSeed, validSeed } from './eclipse-panel-seed.js';
import { queueEntries, registerLocalSeedInput } from './eclipse-execution-scope.js';

const clone = value => JSON.parse(JSON.stringify(value));

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
export function installSeedQueueHook(api, app, controllers, { nodeId, editorKey, usesSeed = () => true, recordQueuedSeed = true }, random = randomSeed) {
    const original = api.queuePrompt;
    const unregister = registerLocalSeedInput(nodeId, usesSeed);
    async function queuePrompt(number, prompt, ...args) {
        const entries = queueEntries(prompt, args[0], node => node.class_type === nodeId);
        if (!entries.length) return original.call(this, number, prompt, ...args);
        const snapshot = clone(prompt), updates = [];
        for (const [id, node] of entries) {
            const config = JSON.parse(node.inputs.configuration), before = clone(config.seed);
            if (!usesSeed(config)) continue;
            if (config.seed.source !== 'local') continue;
            if (!validSeed(config.seed.value) || !['fixed', 'random', 'increment', 'decrement'].includes(config.seed.policy)) throw Error('Enter a valid unsigned 64-bit seed.');
            const seed = { ...config.seed, value: config.seed.policy === 'random' ? random() : config.seed.value };
            config.seed = { ...seed, policy: 'fixed' };
            const raw = JSON.stringify(config); snapshot.output[id].inputs.configuration = raw;
            delete snapshot.output[id].inputs.seed_input;
            const saved = savedNode(snapshot.workflow, id);
            if (saved) {
                saved.widgets_values = [raw]; saved.properties ??= {}; saved.properties[editorKey] ??= {};
                if (recordQueuedSeed) saved.properties[editorKey].lastSeed = seed.value;
            }
            updates.push({ controller: controllers.get(liveNode(app.rootGraph ?? app.graph, id)), before, seed });
        }
        const result = await original.call(this, number, snapshot, ...args);
        if (result?.prompt_id) for (const { controller, before, seed } of updates) {
            if (!controller || controller.disposed || controller.invalid) continue;
            const update = state => {
                if (JSON.stringify(state.config.seed) === JSON.stringify(before)) state.config.seed = nextSeed(seed);
                // Pipes may supply a different seed. Those panels record the
                // server's resolved value and retain it across cached queues.
                if (recordQueuedSeed) state.editor.lastSeed = seed.value;
            };
            if (controller.editQueuedSeed) controller.editQueuedSeed(update);
            else controller.edit(update);
        }
        return result;
    }
    api.queuePrompt = queuePrompt;
    return () => { if (api.queuePrompt === queuePrompt) api.queuePrompt = original; unregister(); };
}
