/**
 * Eclipse Nova — finish the current part, preview its join, then stop.
 * SPDX-License-Identifier: Apache-2.0
 */
import { app, api } from './comfy/index.js';
import { notifyVue } from './eclipse-widget-utils.js';

const CONTROLS = new Set(['Loop Start [Eclipse Nova]', 'Video Loop Start [Eclipse Nova]', 'Loop Control [Eclipse Nova]']);

function executionNode(path) {
    let graph = app.rootGraph ?? app.graph;
    let node;
    for (const id of String(path ?? '').split(':')) {
        node = graph?.getNodeById(id);
        graph = node?.subgraph;
    }
    return node;
}

app.registerExtension({
    name: 'EclipseNova.Loops',
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!CONTROLS.has(nodeData.name)) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            let active = null;
            let requested = false;
            const refresh = () => {
                button.name = requested ? 'Stopping after preview…' : 'Stop after current part';
                notifyVue(this);
                this.setDirtyCanvas(true);
            };
            const button = this.addWidget('button', 'Stop after current part', null, async () => {
                if (!active || requested) return;
                const current = active;
                requested = true;
                refresh();
                try {
                    const response = await api.fetchApi('/eclipse-nova/loop/stop', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ token: current.token, prompt_id: current.prompt_id }),
                    });
                    if (!response.ok) throw new Error((await response.json()).error || 'Stop request failed');
                } catch (error) {
                    if (active === current) { requested = false; refresh(); }
                    app.extensionManager.toast.add({ severity: 'error', summary: 'Loop stop', detail: error.message });
                    this.setDirtyCanvas(true);
                }
            }, { serialize: false });
            button.tooltip = 'While the connected loop runs, finish saving the current part and updating the accumulated preview, then return a partial result. Select that saved run and Resume on the next queue. Connect Loop Control to stop_control before queueing; an idle button has no effect.';
            const reset = () => {
                active = null;
                requested = false;
                refresh();
            };
            const update = event => {
                const data = event.detail;
                if (executionNode(data?.node_id) !== this && executionNode(data?.control_node_id) !== this) return;
                if (data.status !== 'running') {
                    // Late acknowledgements/completion must not replace the next queue's state.
                    if (active?.token !== data.token || active?.prompt_id !== data.prompt_id) return;
                    if (data.status === 'stopping') { requested = true; refresh(); }
                    else reset();
                    return;
                }
                if (active?.token !== data.token) requested = false;
                active = data;
                refresh();
            };
            const finished = event => {
                if (active && (!event.detail?.prompt_id || event.detail.prompt_id === active.prompt_id)) reset();
            };
            api.addEventListener('eclipse-nova.loop', update);
            const events = ['execution_success', 'execution_error', 'execution_interrupted'];
            for (const name of events) api.addEventListener(name, finished);
            const removed = this.onRemoved;
            this.onRemoved = function () {
                api.removeEventListener('eclipse-nova.loop', update);
                for (const name of events) api.removeEventListener(name, finished);
                return removed?.apply(this, arguments);
            };
            return result;
        };
    },
});
