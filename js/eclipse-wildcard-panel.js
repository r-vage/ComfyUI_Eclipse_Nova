/** Structured wildcard editor and live results for standard canvas and Nodes 2.0. */
import { app, api } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { validSeed } from './eclipse-panel-seed.js';
import { installSeedQueueHook } from './eclipse-panel-seed-queue.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, WildcardState } from './eclipse-wildcard-state.js';
import { WildcardForm } from './eclipse-wildcard-form.js';
import { WildcardPreview } from './eclipse-wildcard-preview.js';

const controllers = new WeakMap();
let pendingList;
function wildcardList() {
    // Coalesce concurrent picker opens without scanning other nodes or polling.
    pendingList ??= api.fetchApi('/eclipse-nova/wildcards/list').then(async response => {
        const list = await response.json();
        if (!response.ok || !Array.isArray(list) || list.some(item => typeof item !== 'string')) throw Error('Could not list wildcards.');
        return list;
    }).finally(() => { pendingList = null; });
    return pendingList;
}

class WildcardPanel extends ConfigurationPanel {
    restore(value) { this.previewStatus = ''; super.restore(value); }
    connected(name) { return this.node.inputs?.some(input => input.name === name && input.link != null) === true; }
    hasConnectedValues() {
        return this.connected('wildcard_text') || this.connected('substitutions') || this.state.config.seed.source === 'input';
    }
    cancelPreview() { this.previewer?.cancel(); this.pickerGeneration = (this.pickerGeneration ?? 0) + 1; }
    edit(fn, render = true) {
        const before = this.state.value(); super.edit(fn, render);
        if (before !== this.state.value()) this.preview();
    }
    editQueuedSeed(fn) {
        // Advancing the next seed must not overwrite the just-executed result
        // with a preview of the next run, even when execution beats acceptance.
        this.cancelPreview(); this.previewStatus = ''; super.edit(fn);
    }
    preview(immediate = false) {
        this.cancelPreview(); this.previewStatus = '';
        if (this.disposed || this.invalid || this.state.config.mode === 'fixed') return;
        if (this.hasConnectedValues()) { this.form.syncSummaries(); return; }
        if (!validSeed(this.state.config.seed.value)) { this.previewStatus = 'Enter a valid seed to preview.'; this.form.syncSummaries(); return; }
        this.previewer ??= new WildcardPreview(api.fetchApi.bind(api), result => this.receive(result, 'preview'), message => {
            this.previewStatus = message; this.form.syncSummaries();
        });
        this.previewStatus = 'Updating preview…'; this.form.syncSummaries();
        this.previewer.schedule(this.value(), immediate);
    }
    receive(result, kind = 'run') {
        if (this.disposed || this.invalid || typeof result?.text !== 'string') return;
        this.previewer?.cancel(); this.previewStatus = '';
        // Display results are editor state, never execution input in Populate.
        this.state.editor.preview = { text: result.text, seed: result.seed, kind };
        if (kind === 'run' && validSeed(result.seed)) this.state.editor.lastSeed = result.seed;
        this.node.properties ??= {}; this.node.properties[EDITOR_KEY] = JSON.parse(JSON.stringify(this.state.editor));
        this.form.syncSummaries(); this.node.setDirtyCanvas(true, true);
    }
    resultStatus() {
        if (this.state.config.mode === 'fixed') return 'Fixed text · no wildcard expansion.';
        if (this.previewStatus) return this.previewStatus;
        const last = this.state.editor.preview;
        if (this.hasConnectedValues()) return last?.kind === 'run' ? `Last run · seed ${last.seed}. Connected values update when the workflow runs.` : 'Run the workflow to preview connected inputs.';
        if (!last) return 'Edit Prompt or update the preview. Random seeds are chosen when queued.';
        return `${last.kind === 'run' ? 'Last run' : 'Preview'} · seed ${last.seed}${this.state.config.seed.policy === 'random' ? ' · random changes when queued' : ''}`;
    }
    syncConnection(restored = false) {
        if (this.disposed || this.invalid || !this.node.graph || (app.configuringGraph && !restored)) return;
        this.cancelPreview(); this.previewStatus = '';
        if (!this.connected('seed_input') && this.state.config.seed.source === 'input') {
            // Restore a valid local seed on disconnect, without eager previews on load.
            super.edit(state => state.setLocalSeed(true, false));
        } else this.form.render();
    }
    async openWildcards(trigger, input) {
        if (this.form.menu.trigger === trigger) { this.form.menu.close(true); return; }
        const generation = this.pickerGeneration = (this.pickerGeneration ?? 0) + 1;
        const start = input.selectionStart, end = input.selectionEnd;
        try {
            const list = await wildcardList();
            if (this.disposed || generation !== this.pickerGeneration || !trigger.isConnected) return;
            this.form.menu.open(trigger, 'Wildcards', '', list, token => {
                try {
                    let caret;
                    this.edit(state => { caret = state.insertWildcard(token, start, end); }, false);
                    input.value = this.state.config.texts.prompt; input.focus({ preventScroll: true }); input.setSelectionRange(caret, caret);
                } catch (error) { this.previewStatus = error.message; this.form.syncSummaries(); }
            });
        } catch (error) {
            if (!this.disposed && generation === this.pickerGeneration) { this.previewStatus = error.message; this.form.syncSummaries(); }
        }
    }
    async reloadWildcards(trigger) {
        trigger.disabled = true;
        try {
            const response = await api.fetchApi('/eclipse-nova/wildcards/refresh'); const result = await response.json();
            if (!response.ok || !result.success) throw Error(result.message || 'Could not reload wildcards.');
            if (!this.disposed) this.preview(true);
        } catch (error) { if (!this.disposed) { this.previewStatus = error.message; this.form.syncSummaries(); } }
        finally { trigger.disabled = false; }
    }
}

app.registerExtension({
    name: 'EclipseNova.WildcardListPanel',
    setup() {
        ensurePanelStyle();
        installSeedQueueHook(api, app, controllers, { nodeId: NODE_ID, editorKey: EDITOR_KEY, usesSeed: config => config.mode === 'populate' });
    },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new WildcardPanel(node, name, inputData[1], {
                State: WildcardState, Form: WildcardForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-wildcard', label: 'Wildcard Processor editor', onDispose: node => controllers.delete(node),
                fillHeight: true, minHeight: 180,
            });
            controller.widget.options.socketless = true;
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 430, minHeight: 450 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== NODE_ID) return;
        for (const method of ['onConfigure', 'onAdded', 'onGraphConfigured', 'onConnectionsChange']) {
            const original = nodeType.prototype[method];
            nodeType.prototype[method] = function (...args) {
                const result = original?.apply(this, args), controller = controllers.get(this);
                if (controller) {
                    if (method === 'onConfigure') controller.restore(controller.value());
                    controller.bindHost();
                    if (method !== 'onConfigure') controller.syncConnection(method === 'onGraphConfigured');
                }
                return result;
            };
        }
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (output, ...args) {
            const result = executed?.call(this, output, ...args); controllers.get(this)?.receive(output?.eclipse_wildcard?.[0]); return result;
        };
    },
});
