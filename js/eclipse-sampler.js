/** Eclipse Nova structured sampler editors, mounted identically in both renderers. */
import { app, api } from './comfy/index.js';
import { NODE_IDS, SETTINGS_ID, WIDGET_TYPE, EDITOR_KEY, SamplerState, clone, validSeed, nextSeed } from './eclipse-sampler-state.js';
import { SamplerForm } from './eclipse-sampler-form.js';
import { installQueueHook } from './eclipse-sampler-queue.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { PanelNumbers } from './eclipse-panel-numbers.js';
import { DetailerPreview, installDetailerPreviews } from './eclipse-detailer-preview.js';

const controllers = new WeakMap(), graphKey = Symbol('EclipseNova.PanelGraph');
export class SamplerController {
    constructor(node, name, options) {
        this.node = node; this.spec = options.editorSpec; this.raw = options.default;
        this.state = new SamplerState(this.raw, this.spec); this.height = 0;
        const detailer = this.spec.profile !== 'settings';
        this.root = document.createElement('div'); this.root.className = 'en-panel'; this.root.dataset.profile = this.spec.profile;
        if (detailer) this.root.classList.add('en-panel-fill-height');
        this.root.setAttribute('aria-label', { settings: 'Smart sampler settings', sampler: 'Eclipse sampler settings', detailer: 'Detailer settings', advanced: 'Advanced sampler settings' }[this.spec.profile]);
        this.root.onpointerdown = event => event.stopPropagation(); this.root.onkeydown = event => event.stopPropagation();
        this.numbers = new PanelNumbers(this.root, () => this.measure());
        this.widget = node.addDOMWidget(name, WIDGET_TYPE, this.root, {
            getValue: () => this.value(), setValue: value => this.restore(value),
            ...(detailer ? { getMinHeight: () => this.height + 8 } : {
                getMinHeight: () => this.height, getMaxHeight: () => this.height, getHeight: () => this.height,
            }),
            hideOnZoom: false, serialize: true, margin: detailer ? 4 : 0,
        });
        this.widget.serializeValue = () => this.value();
        if (detailer) this.preview = new DetailerPreview(this);
        else this.widget.computeSize = () => [320, this.height];
        this.form = new SamplerForm(this);
        this.observer = new ResizeObserver(() => this.measure()); this.observer.observe(this.root);
        this.form.render();
        const remove = this.widget.onRemove.bind(this.widget);
        this.widget.onRemove = () => { this.dispose(); remove(); };
    }
    value() { return this.invalid ? this.raw : this.state.value(); }
    restore(value) {
        if (this.editing) return;
        this.raw = value; this.form?.menu.close();
        try {
            this.state = new SamplerState(value, this.spec, this.node.properties?.[EDITOR_KEY] ?? {});
            this.invalid = false; this.root.classList.remove('en-panel-error'); this.form?.render();
        } catch (error) {
            this.invalid = true; this.root.classList.add('en-panel-error');
            const message = document.createElement('div'); message.textContent = `Cannot edit configuration: ${error.message}`;
            this.root.replaceChildren(message);
            this.measure();
        }
    }
    edit(fn, render = true) {
        if (this.disposed || this.invalid) return;
        const graph = this.node.graph;
        graph?.beforeChange(); graph?.canvasAction(canvas => canvas.emitBeforeChange()); this.editing = true;
        try {
            fn(this.state); this.node.properties ??= {}; this.node.properties[EDITOR_KEY] = clone(this.state.editor);
            this.raw = this.state.value(); this.widget.callback?.(this.raw);
        } finally {
            this.editing = false; graph?.afterChange(); graph?.canvasAction(canvas => canvas.emitAfterChange());
        }
        if (render) this.form.render();
        else this.form.syncSummaries();
        this.numbers.sync();
        this.node.setDirtyCanvas(true, true);
    }
    bindHost() {
        if (!this.node.graph || this.disposed) return;
        const owner = `${this.node.graph[graphKey] ??= crypto.randomUUID()}/${this.node.id}`;
        this.root.dataset.enOwner = owner;
        // ComfyUI can retain a WidgetDOM host across undo while replacing its widget.
        for (const previous of document.querySelectorAll('.en-panel[data-en-owner]')) {
            if (previous !== this.root && previous.dataset.enOwner === owner) previous.replaceWith(this.root);
        }
        this.measure();
    }
    measure() {
        this.numbers?.sync();
        if (this.disposed || this.frame) return;
        this.frame = requestAnimationFrame(() => {
            this.frame = null; if (!this.root.isConnected || !this.root.offsetWidth) return;
            const detailer = !!this.preview, preview = this.preview?.visible ?? false;
            const controls = detailer && !this.invalid ? this.form.controls : this.root.firstElementChild;
            const height = Math.ceil((controls?.offsetHeight ?? this.root.scrollHeight) + 16 + (preview ? 108 : 0));
            if (height <= 16 || (height === this.height && preview === this.measuredPreview)) return;
            this.height = height;
            this.measuredPreview = preview;
            for (const key of detailer ? ['min-height'] : ['height', 'min-height', 'max-height']) this.root.style.setProperty(`--comfy-widget-${key}`, `${height}px`);
            const size = this.node.computeSize();
            const retainHeight = ['sampler', 'advanced'].includes(this.spec.profile) || preview;
            this.node.setSize([Math.max(320, this.node.size[0]), retainHeight ? Math.max(this.node.size[1], size[1]) : size[1]]);
            this.node.setDirtyCanvas(true, true);
        });
    }
    dispose() {
        if (this.disposed) return;
        this.disposed = true; this.observer.disconnect(); this.numbers.dispose(); this.form.dispose(); this.preview?.dispose();
        if (this.frame) cancelAnimationFrame(this.frame); controllers.delete(this.node);
    }
}

app.registerExtension({
    name: 'EclipseNova.SamplerV2',
    setup() {
        ensurePanelStyle(); installQueueHook(api, app, controllers); installDetailerPreviews();
    },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new SamplerController(node, name, inputData[1]); controllers.set(node, controller);
            return { widget: controller.widget, minWidth: 400 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (!NODE_IDS.has(data.name)) return;
        if (data.name !== SETTINGS_ID) {
            Object.defineProperty(nodeType.prototype, 'hideOutputImages', { configurable: true, get() { return true; } });
            const executed = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (output, ...args) {
                const { images: _images, ...withoutImages } = output;
                const result = executed?.call(this, withoutImages, ...args);
                const controller = controllers.get(this), seed = output?.eclipse_seed?.[0];
                if (controller && validSeed(seed)) controller.edit(state => {
                    const submitted = output?.eclipse_local_seed?.[0];
                    if (submitted && state.config.parameters.allow_overwrite
                        && JSON.stringify(state.config.seed) === JSON.stringify(submitted)) {
                        state.config.seed = nextSeed({ ...submitted, value: seed });
                    }
                    state.editor.lastSeed = seed;
                });
                controller?.preview.complete(output);
                return result;
            };
        }
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
