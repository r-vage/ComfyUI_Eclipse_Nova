/** Resolve once per graph serialization, shared with wildcard seed consumers. */
import { nextSeed } from './eclipse-panel-seed.js';
import { executionScope } from './eclipse-execution-scope.js';
import { NODE_ID, EDITOR_KEY, StandaloneSeedState } from './eclipse-seed-state.js';
import { enterGraphToPromptHook, exitGraphToPromptHook, getGraphNodeList, hasCurrentQueuedSeed,
    storeQueuedSeed, findWorkflowNode } from './eclipse-seed-utils.js';

function liveNode(graph, key) {
    const parts = String(key).split(':');
    let node;
    for (const id of parts) { node = graph?.getNodeById(id); graph = node?.subgraph; }
    return node;
}

function fixedConfiguration(state, value) {
    return JSON.stringify({ ...state.config, seed: { value, policy: 'fixed' } });
}

function saveWorkflow(snapshot, id, raw, value) {
    const node = findWorkflowNode(snapshot.workflow, id);
    if (!node) return;
    node.widgets_values = [raw]; node.properties ??= {};
    node.properties[EDITOR_KEY] = { ...node.properties[EDITOR_KEY], lastSeed: value };
}

export function resolveNodeSeed(controller) {
    if (!controller || controller.invalid || !controller.state.validSeed(controller.state.config.seed.value)) return null;
    const { node, state } = controller, raw = controller.value();
    if (hasCurrentQueuedSeed(node, '_Eclipse_queuedSeed') && controller.resolution?.raw === raw) return node._Eclipse_queuedSeed;
    const value = state.config.seed.policy === 'random' ? state.randomSeed() : state.config.seed.value;
    storeQueuedSeed(node, value); controller.resolution = { raw, value }; return value;
}

export function installStandaloneSeedHooks(api, app, controllers) {
    const originalGraph = app.graphToPrompt, originalQueue = api.queuePrompt;
    // Cached nodes publish no onExecuted event. Match their actual execution to
    // this client's accepted snapshot, including events arriving before the reply.
    const pendingCache = new Map(), earlyCache = new Map();
    const boundedSet = (map, key, value) => { map.set(key, value); while (map.size > 32) map.delete(map.keys().next().value); };
    const recordCached = (updates, ids) => {
        for (const { id, node, controller, value } of updates) {
            if (!ids.has(String(id)) || !controller || controller.disposed || controller.invalid
                || liveNode(app.rootGraph ?? app.graph, id) !== node || controllers.get(node) !== controller) continue;
            controller.edit(state => state.record(value));
        }
    };
    const cached = event => {
        const { prompt_id: id, nodes } = event.detail ?? {};
        if (!id || !Array.isArray(nodes)) return;
        const ids = new Set(nodes.map(String)), updates = pendingCache.get(id);
        if (updates) { pendingCache.delete(id); recordCached(updates, ids); }
        else boundedSet(earlyCache, id, ids);
    };
    api.addEventListener?.('execution_cached', cached);
    const graphHook = async function (...args) {
        enterGraphToPromptHook();
        try {
            const entries = getGraphNodeList(app.rootGraph ?? app.graph);
            const snapshot = await originalGraph.apply(this, args);
            for (const { node, outputKey } of entries) {
                if (node.type !== NODE_ID || [2, 4].includes(node.mode) || !snapshot.output?.[outputKey]) continue;
                const controller = controllers.get(node);
                // Only freeze here if a serialization consumer explicitly asked
                // for this seed. Ordinary seeds resolve at queue time, when the
                // partial-execution targets are available.
                if (!controller || !hasCurrentQueuedSeed(node, '_Eclipse_queuedSeed')
                    || controller.resolution?.raw !== controller.value()) continue;
                const value = node._Eclipse_queuedSeed;
                const raw = fixedConfiguration(controller.state, value);
                snapshot.output[outputKey].inputs.configuration = raw;
                const saved = findWorkflowNode(snapshot.workflow, outputKey);
                controller.pendingSeed = { raw, before: controller.value(), value,
                    saved: saved ? structuredClone(saved) : null };
                saveWorkflow(snapshot, outputKey, raw, value);
            }
            return snapshot;
        } finally { exitGraphToPromptHook(); }
    };
    const queueHook = async function (number, prompt, ...rest) {
        const entries = Object.entries(prompt?.output ?? {}).filter(([, node]) => node.class_type === NODE_ID);
        if (!entries.length) return originalQueue.call(this, number, prompt, ...rest);
        const snapshot = structuredClone(prompt), updates = [], scope = executionScope(prompt, rest[0]);
        for (const [id, entry] of entries) {
            const raw = entry.inputs?.configuration;
            const node = liveNode(app.rootGraph ?? app.graph, id), controller = controllers.get(node);
            const pending = controller?.pendingSeed?.raw === raw ? controller.pendingSeed : null;
            if (scope && !scope.has(id)) {
                if (pending) {
                    snapshot.output[id].inputs.configuration = pending.before;
                    const saved = findWorkflowNode(snapshot.workflow, id);
                    if (saved && pending.saved) {
                        saved.widgets_values = pending.saved.widgets_values;
                        if (pending.saved.properties) saved.properties = pending.saved.properties;
                        else delete saved.properties;
                    }
                }
                continue;
            }
            let state;
            try { state = new StandaloneSeedState(raw); } catch { continue; }
            if (!state.validSeed(state.config.seed.value)) continue; // Backend supplies the validation message.
            const value = pending?.value ?? (state.config.seed.policy === 'random' ? state.randomSeed() : state.config.seed.value);
            const resolved = fixedConfiguration(state, value);
            snapshot.output[id].inputs.configuration = resolved; saveWorkflow(snapshot, id, resolved, value);
            updates.push({ id, node, controller, value, before: pending?.before ?? state.value() });
        }
        const result = await originalQueue.call(this, number, snapshot, ...rest);
        if (!result?.prompt_id) return result;
        for (const { node, controller, before, value } of updates) {
            if (!controller || controller.disposed || controller.invalid || controllers.get(node) !== controller) continue;
            storeQueuedSeed(node, value);
            controller.edit(state => {
                if (state.value() === before) state.config.seed = nextSeed({ ...state.config.seed, value }, state.maxSeed);
                state.editor.lastSeed = value;
            });
            controller.pendingSeed = null;
        }
        const cachedIds = earlyCache.get(result.prompt_id);
        if (cachedIds) { earlyCache.delete(result.prompt_id); recordCached(updates, cachedIds); }
        else boundedSet(pendingCache, result.prompt_id, updates);
        return result;
    };
    app.graphToPrompt = graphHook; api.queuePrompt = queueHook;
    return () => {
        if (app.graphToPrompt === graphHook) app.graphToPrompt = originalGraph;
        if (api.queuePrompt === queueHook) api.queuePrompt = originalQueue;
        api.removeEventListener?.('execution_cached', cached); pendingCache.clear(); earlyCache.clear();
    };
}
