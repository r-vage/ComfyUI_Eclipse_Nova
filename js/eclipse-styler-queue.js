/** Freeze the selected style for a real submission; only acceptance advances it. */
import { NODE_ID, EDITOR_KEY, StylerState, clone, resolveSelection, acceptSelection } from './eclipse-styler-state.js';
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
export function installStylerQueueHook(api, app, controllers, loadNames, random = Math.random) {
    const original = api.queuePrompt;
    async function queuePrompt(number, prompt, ...args) {
        const entries = queueEntries(prompt, args[0], node => node.class_type === NODE_ID);
        if (!entries.length) return original.call(this, number, prompt, ...args);
        const snapshot = clone(prompt), updates = [], catalogs = new Map();
        for (const [id, node] of entries) {
            const state = new StylerState(node.inputs.configuration), config = state.config;
            if (!config.apply_to_positive && !config.apply_to_negative) continue;
            const controller = controllers.get(liveNode(app.rootGraph ?? app.graph, id));
            if (!catalogs.has(config.style_mode)) catalogs.set(config.style_mode, loadNames(config.style_mode));
            const names = await catalogs.get(config.style_mode);
            const selected = resolveSelection(config, names, controller?.state.editor.lastStyle, random);
            const raw = JSON.stringify({ ...config, style: selected.style, index: selected.index, policy: 'fixed' });
            snapshot.output[id].inputs.configuration = raw;
            const saved = savedNode(snapshot.workflow, id);
            if (saved) {
                saved.widgets_values = [raw]; saved.properties ??= {}; saved.properties[EDITOR_KEY] ??= {};
                saved.properties[EDITOR_KEY].lastStyle = clone(selected);
            }
            updates.push({ controller, config, selected, names });
        }
        const result = await original.call(this, number, snapshot, ...args);
        if (result?.prompt_id) for (const { controller, config, selected, names } of updates) {
            if (controller && !controller.disposed && !controller.invalid) controller.edit(state => acceptSelection(state, config, selected, names));
        }
        return result;
    }
    api.queuePrompt = queuePrompt;
    return () => { if (api.queuePrompt === queuePrompt) api.queuePrompt = original; };
}
