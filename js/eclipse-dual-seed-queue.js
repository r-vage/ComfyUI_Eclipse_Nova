/** Freeze both values on accepted queues, including partial execution and cache hits. */
import { nextSeed } from './eclipse-panel-seed.js';
import { executionScope } from './eclipse-execution-scope.js';
import { findWorkflowNode } from './eclipse-seed-utils.js';
import { NODE_ID, EDITOR_KEY, KEYS, DualSeedState } from './eclipse-dual-seed-state.js';
function liveNode(graph, id) {
    let node;
    for (const part of String(id).split(':')) { node = graph?.getNodeById(part); graph = node?.subgraph; }
    return node;
}
export function installDualSeedHooks(api, app, controllers) {
    const original = api.queuePrompt, pending = new Map(), early = new Map();
    const store = (map, key, value) => { map.set(key, value); while (map.size > 32) map.delete(map.keys().next().value); };
    const valid = item => item.controller && !item.controller.invalid && !item.controller.disposed
        && controllers.get(item.node) === item.controller && liveNode(app.rootGraph ?? app.graph, item.id) === item.node;
    const record = (items, ids) => { for (const item of items) if (ids.has(String(item.id)) && valid(item))
        item.controller.edit(state => state.record(item.values)); };
    const cached = event => {
        const { prompt_id: id, nodes } = event.detail ?? {};
        if (!id || !Array.isArray(nodes)) return;
        const ids = new Set(nodes.map(String));
        if (pending.has(id)) { record(pending.get(id), ids); pending.delete(id); }
        else store(early, id, ids);
    };
    api.addEventListener?.('execution_cached', cached);
    const hook = async function(number, prompt, ...rest) {
        const entries = Object.entries(prompt?.output ?? {}).filter(([, n]) => n.class_type === NODE_ID);
        if (!entries.length) return original.call(this, number, prompt, ...rest);
        const snapshot = structuredClone(prompt), updates = [], scope = executionScope(prompt, rest[0]);
        for (const [id, entry] of entries) {
            if (scope && !scope.has(id)) continue;
            let state;
            try { state = new DualSeedState(entry.inputs?.configuration); } catch { continue; }
            if (!KEYS.every(key => state.channel(key).validSeed(state.config.seeds[key].value))) continue;
            const before = state.value(), values = KEYS.map(key => state.config.seeds[key].policy === 'random'
                ? state.channel(key).randomSeed() : state.config.seeds[key].value);
            KEYS.forEach((key, i) => { state.config.seeds[key] = { value: values[i], policy: 'fixed' }; });
            const raw = state.value(); snapshot.output[id].inputs.configuration = raw;
            const saved = findWorkflowNode(snapshot.workflow, id);
            if (saved) {
                saved.widgets_values = [raw];
                if (saved.widgets_values_named) saved.widgets_values_named.configuration = raw;
                saved.properties ??= {};
                saved.properties[EDITOR_KEY] = { ...saved.properties[EDITOR_KEY], lastSeeds: Object.fromEntries(KEYS.map((key, i) => [key, values[i]])) };
            }
            const node = liveNode(app.rootGraph ?? app.graph, id);
            updates.push({ id, node, controller: controllers.get(node), before, values });
        }
        const result = await original.call(this, number, snapshot, ...rest);
        if (!result?.prompt_id) return result;
        for (const item of updates) if (valid(item)) item.controller.edit(state => {
            if (state.value() === item.before) KEYS.forEach((key, i) => {
                state.config.seeds[key] = nextSeed({ ...state.config.seeds[key], value: item.values[i] }, state.channel(key).maxSeed);
            });
            KEYS.forEach((key, i) => { state.editor.lastSeeds[key] = item.values[i]; });
        });
        if (early.has(result.prompt_id)) { record(updates, early.get(result.prompt_id)); early.delete(result.prompt_id); }
        else store(pending, result.prompt_id, updates);
        return result;
    };
    api.queuePrompt = hook;
    return () => {
        if (api.queuePrompt === hook) api.queuePrompt = original;
        api.removeEventListener?.('execution_cached', cached); pending.clear(); early.clear();
    };
}
