/** Prompt Styler's single structured editor for standard canvas and Nodes 2.0. */
import { app, api } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, StylerState } from './eclipse-styler-state.js';
import { StylerForm } from './eclipse-styler-form.js';
import { installStylerQueueHook } from './eclipse-styler-queue.js';

const controllers = new WeakMap();
async function request(path, signal) {
    const response = await api.fetchApi(`/eclipse-nova/prompt_styler${path}`, { signal, cache: 'no-store' });
    if (!response.ok) throw Error(`Could not read style files (${response.status}).`);
    return response.json();
}
async function loadNames(mode, signal) { return (await request(`/styles/${encodeURIComponent(mode)}`, signal)).styles; }

class StylerPanel extends ConfigurationPanel {
    get styles() { return this.catalog ?? this.spec.styles; }
    names() { return this.styles[this.state.config.style_mode] ?? []; }
    async refresh() {
        if (this.disposed || this.loading) return;
        this.loading = true; this.message = 'Refreshing style files…'; this.events ??= new AbortController(); this.form.render();
        try {
            await request('/reload', this.events.signal);
            const entries = await Promise.all(Object.keys(this.spec.styles).map(async mode => [mode, await loadNames(mode, this.events.signal)]));
            if (this.disposed) return;
            this.catalog = Object.fromEntries(entries); this.message = '';
        } catch (error) { if (!this.disposed) this.message = error.message; }
        finally { if (!this.disposed) { this.loading = false; if (!this.invalid) this.form.render(); } }
    }
    dispose() { this.events?.abort(); super.dispose(); }
}

app.registerExtension({
    name: 'EclipseNova.PromptStylerPanel',
    setup() { ensurePanelStyle(); installStylerQueueHook(api, app, controllers, loadNames); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new StylerPanel(node, name, inputData[1], {
                State: StylerState, Form: StylerForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-styler', label: 'Prompt Styler editor', onDispose: node => controllers.delete(node),
            });
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 390 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== NODE_ID) return;
        const configure = nodeType.prototype.onConfigure, added = nodeType.prototype.onAdded;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configure?.apply(this, args), controller = controllers.get(this);
            if (controller) { controller.restore(controller.value()); controller.bindHost(); } return result;
        };
        nodeType.prototype.onAdded = function (...args) {
            const result = added?.apply(this, args); controllers.get(this)?.bindHost(); return result;
        };
    },
});
