/** Smart Prompt's single structured editor for classic canvas and Nodes 2.0. */
import { app, api } from './comfy/index.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, PromptState, clone } from './eclipse-smart-prompt-state.js';
import { validSeed } from './eclipse-panel-seed.js';
import { PromptForm } from './eclipse-smart-prompt-form.js';
import { installPromptQueueHook } from './eclipse-smart-prompt-queue.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { PromptLibrary } from './eclipse-smart-prompt-library.js';
import { captureFocusedTextWheel, fitNodeToWidgets, forwardCanvasNavigation } from './eclipse-widget-utils.js';

const controllers = new WeakMap(), graphKey = Symbol('EclipseNova.PromptGraph');
const library = new PromptLibrary((...args) => api.fetchApi(...args));
export class PromptController {
    constructor(node, name, options) {
        this.node = node; this.raw = options.default; this.state = new PromptState(this.raw); this.height = 0;
        this.catalog = { folders: [] }; this.files = new Map(); this.fileRequests = new Map(); this.revision = 0; this.events = new AbortController();
        this.root = document.createElement('div'); this.root.className = 'en-panel en-prompt'; this.root.setAttribute('aria-label', 'Smart Prompt editor');
        this.root.onpointerdown = event => event.stopPropagation(); this.root.onkeydown = event => event.stopPropagation();
        this.disposeNavigation = forwardCanvasNavigation(this.root);
        this.disposeTextWheel = captureFocusedTextWheel(this.root);
        this.widget = node.addDOMWidget(name, WIDGET_TYPE, this.root, {
            getValue: () => this.value(), setValue: value => this.restore(value),
            getMinHeight: () => this.height, getMaxHeight: () => this.height, getHeight: () => this.height,
            hideOnZoom: false, serialize: true, margin: 0,
        });
        this.widget.serializeValue = () => this.value(); this.widget.computeSize = () => [this.node.size[0], this.height];
        this.form = new PromptForm(this); this.observer = new ResizeObserver(() => this.measure()); this.observer.observe(this.root); this.form.render();
        const remove = this.widget.onRemove.bind(this.widget); this.widget.onRemove = () => { this.dispose(); remove(); };
    }
    value() { return this.invalid ? this.raw : this.state.value(); }
    restore(value) {
        if (this.editing || this.disposed) return;
        this.raw = value; this.form.menu.close(); this.form.drag.cancel(); this.closeEditor?.();
        try {
            this.state = new PromptState(value, this.node.properties?.[EDITOR_KEY] ?? {}); this.invalid = false; this.form.render();
        } catch (error) { this.invalid = true; const message = document.createElement('div'); message.className = 'en-panel-error'; message.textContent = `Cannot edit configuration: ${error.message}`; this.root.replaceChildren(message); this.measure(); }
    }
    edit(fn, render = true) {
        if (this.disposed || this.invalid) return;
        const graph = this.node.graph; graph?.beforeChange(); graph?.canvasAction(canvas => canvas.emitBeforeChange()); this.editing = true;
        try {
            fn(this.state); this.node.properties ??= {}; this.node.properties[EDITOR_KEY] = clone(this.state.editor);
            this.raw = this.state.value(); this.widget.callback?.(this.raw);
        } finally { this.editing = false; graph?.afterChange(); graph?.canvasAction(canvas => canvas.emitAfterChange()); }
        if (render) this.form.render(); else this.form.syncSummaries(); this.node.setDirtyCanvas(true, true);
    }
    connected() { return this.node.inputs?.find(input => input.name === 'seed_input')?.link != null; }
    syncConnection(restored = false) {
        if (this.disposed || this.invalid || !this.node.graph || (app.configuringGraph && !restored)) return;
        if (!this.connected() && this.state.config.seed.source === 'input') this.edit(state => state.setLocalSeed(true, false));
        else this.form.render();
    }
    bindHost() {
        if (!this.node.graph || this.disposed) return;
        const owner = `${this.node.graph[graphKey] ??= crypto.randomUUID()}/${this.node.id}`; this.root.dataset.enOwner = owner;
        for (const previous of document.querySelectorAll('.en-prompt[data-en-owner]')) if (previous !== this.root && previous.dataset.enOwner === owner) previous.replaceWith(this.root);
        if (!this.started) { this.started = true; this.refresh(true); }
        this.measure();
    }
    request(path, options = {}) {
        return library.request(path, { signal: this.events.signal, ...options });
    }
    async getFile(path, load = null) {
        const revision = (this.fileRequests.get(path) ?? 0) + 1; this.fileRequests.set(path, revision);
        const url = `/file?${new URLSearchParams({ path })}`;
        const data = await (load ? load.read(url) : this.request(url));
        if (!this.disposed && revision === this.fileRequests.get(path)) this.cacheFile(data);
        return data;
    }
    cacheFile(data) {
        this.fileRequests.set(data.id, (this.fileRequests.get(data.id) ?? 0) + 1);
        this.files.set(data.id, data);
    }
    async refresh(initial = false) {
        if (this.disposed || this.loading) return;
        const load = initial ? library.beginLoad(this.node.graph.rootGraph ?? this.node.graph, this.events.signal) : null;
        const revision = ++this.revision; this.loading = true; this.message = 'Refreshing prompt files…';
        try {
            if (!this.invalid) this.form.render();
            const catalog = await (load ? load.read('/catalog') : this.request('/catalog'));
            const paths = new Set(catalog.folders.flatMap(folder => folder.files.map(file => file.id)));
            const cached = [...new Set([...this.files.keys(), ...this.state.config.folders.flatMap(folder => folder.files.map(file => file.id))])].filter(path => paths.has(path));
            const results = [];
            for (let index = 0; index < cached.length && !this.disposed; index += 8) {
                // A picker/editor opened during startup owns the newer read for its file.
                const paths = cached.slice(index, index + 8).filter(path => !load || !this.fileRequests.has(path));
                results.push(...await Promise.allSettled(paths.map(path => this.getFile(path, load))));
            }
            if (this.disposed || revision !== this.revision) return;
            this.catalog = catalog; for (const path of this.files.keys()) if (!paths.has(path)) this.files.delete(path);
            const failed = results.filter(result => result.status === 'rejected').length;
            this.message = failed ? `Refreshed. ${failed} file(s) could not be read.` : '';
        } catch (error) { if (!this.disposed) this.message = error.message; }
        finally {
            load?.close();
            if (!this.disposed && revision === this.revision) { this.loading = false; if (!this.invalid) this.form.render(); }
        }
    }
    measure() {
        if (this.disposed || this.frame) return;
        this.frame = requestAnimationFrame(() => {
            this.frame = null; if (!this.root.isConnected || !this.root.offsetWidth) return;
            const height = Math.ceil((this.root.firstElementChild?.offsetHeight ?? this.root.scrollHeight) + 16); if (height <= 16 || height === this.height) return;
            this.height = height;
            for (const key of ['height', 'min-height', 'max-height']) this.root.style.setProperty(`--comfy-widget-${key}`, `${height}px`);
            fitNodeToWidgets(this.node); this.node.setDirtyCanvas(true, true);
        });
    }
    dispose() {
        if (this.disposed) return;
        this.disposed = true; this.revision++; this.events.abort(); this.observer.disconnect(); this.disposeNavigation(); this.disposeTextWheel(); this.form.dispose(); this.closeEditor?.(); this.files.clear(); this.fileRequests.clear();
        if (this.frame) cancelAnimationFrame(this.frame); controllers.delete(this.node);
    }
}

app.registerExtension({
    name: 'EclipseNova.SmartPrompt',
    setup() { ensurePanelStyle(); installPromptQueueHook(api, app, controllers); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new PromptController(node, name, inputData[1]); controllers.set(node, controller); return { widget: controller.widget, minWidth: 430 };
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
            const result = executed?.call(this, output, ...args), controller = controllers.get(this);
            if (controller && typeof output?.eclipse_prompt?.[0] === 'string') controller.edit(state => {
                state.editor.lastResult = output.eclipse_prompt[0];
                if (validSeed(output.eclipse_seed?.[0])) state.editor.lastSeed = output.eclipse_seed[0];
            });
            return result;
        };
    },
});
