/** Structured Save Images panel with an adaptive batch preview. */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { createDOMPreview, feedDOMPreview } from './eclipse-dom-preview.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, SaveImagesState } from './eclipse-save-images-state.js';
import { SaveImagesForm } from './eclipse-save-images-form.js';

const controllers = new WeakMap();

class SaveImagesPanel extends ConfigurationPanel {
    constructor(node, name, options) {
        super(node, name, options, {
            State: SaveImagesState, Form: SaveImagesForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
            className: 'en-save-images', label: 'Save Images editor',
            fillHeight: true, minHeight: 280,
            onDispose: node => { node._eclipseDomPreview?.dispose(); controllers.delete(node); },
        });
        this.widget.options.socketless = true;
        // Only controls establish the minimum. Allocated image space must never
        // feed back into node sizing, including when the renderer is switched.
        this.observer = new ResizeObserver(() => this.measure()); this.observer.observe(this.form.controls);
    }
    mountPreview() {
        if (this.preview || this.disposed) return;
        this.preview = createDOMPreview(this.node, { noWidget: true, freeResize: true, minHeight: 100 });
        const preview = this.node._eclipseDomPreview;
        preview.container.setAttribute('aria-label', 'Saved image preview');
        preview.container.classList.add('en-review-preview-content'); preview.container.style.height = '';
        preview.container.style.background = 'transparent';
        preview.img.alt = 'Saved image'; preview.img.style.width = '100%'; preview.img.style.height = '100%';
        this.node.hideOutputImages = true;
        this.form.render();
    }
    syncPreview() {
        if (!this.preview) return;
        const hidden = !this.state.config.options.show_previews;
        const preview = this.node._eclipseDomPreview;
        preview.state.hidden = hidden;
        preview.container.style.display = hidden ? 'none' : 'flex';
    }
    measure() {
        if (this.disposed || this.frame) return;
        this.frame = requestAnimationFrame(() => {
            this.frame = null; if (!this.root.isConnected || !this.root.offsetWidth) return;
            const preview = !this.invalid && this.state.config.options.show_previews;
            const controls = this.invalid ? this.root.firstElementChild : this.form.controls;
            const height = Math.ceil((controls?.offsetHeight ?? 0) + 16 + (preview ? 108 : 0));
            if (height <= 16) return;
            if (height === this.height && preview === this.measuredPreview) return;
            this.height = height; this.profile.minHeight = height; this.measuredPreview = preview;
            this.root.style.setProperty('--comfy-widget-min-height', `${height}px`);
            const size = this.node.computeSize();
            this.node.setSize([Math.max(340, this.node.size[0]), preview ? Math.max(this.node.size[1], size[1]) : size[1]]);
            this.node.setDirtyCanvas(true, true);
        });
    }
}

function suppressNativePreview(node) {
    node.hideOutputImages = true; node.imgs = null; node.imageIndex = null;
    const graph = node.graph, subgraph = graph?.isRootGraph === false || (graph?.rootGraph && graph.rootGraph !== graph);
    const key = subgraph && graph.id != null ? `${graph.id}:${node.id}` : String(node.id);
    const output = app.nodeOutputs?.[key];
    queueMicrotask(() => { if (output?.images) delete output.images; node.imgs = null; });
}

app.registerExtension({
    name: 'EclipseNova.SaveImagesPanel',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new SaveImagesPanel(node, name, inputData[1]); controllers.set(node, controller);
            return { widget: controller.widget, minWidth: 400, minHeight: 370 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== NODE_ID) return;
        const created = nodeType.prototype.onNodeCreated, added = nodeType.prototype.onAdded,
            configure = nodeType.prototype.onConfigure, executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args); controllers.get(this)?.mountPreview(); return result;
        };
        nodeType.prototype.onAdded = function (...args) {
            const result = added?.apply(this, args); controllers.get(this)?.bindHost(); return result;
        };
        nodeType.prototype.onConfigure = function (...args) {
            const result = configure?.apply(this, args), controller = controllers.get(this);
            if (controller) { controller.restore(controller.value()); controller.bindHost(); } return result;
        };
        nodeType.prototype.onExecuted = function (output) {
            const { images: _images, ...withoutImages } = output;
            const result = executed?.call(this, withoutImages), controller = controllers.get(this);
            const images = controller?.state.config.options.show_previews ? output.images ?? [] : [];
            feedDOMPreview(this, { images }, { publish: false }); suppressNativePreview(this); return result;
        };
    },
});
