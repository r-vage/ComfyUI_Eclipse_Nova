/** Stop-capable DOM displays using the shared themed configuration panel. */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { element, button, ensurePanelStyle } from './eclipse-panel-controls.js';
import { runActions } from './eclipse-panel-run.js';
import { createDOMTextController, DOM_TEXT_PREVIEW_NAME } from './eclipse-dom-text.js';
import { createDOMPreview, feedDOMPreview } from './eclipse-dom-preview.js';
import { publishSubgraphDOMPreview, registerSubgraphDOMPreviewProvider } from './eclipse-subgraph-dom-previews.js';

export const WIDGET_TYPE = 'ECLIPSE_NOVA_REVIEW_PREVIEW';
export const NODE_IDS = ['Show Any Stop [Eclipse Nova]', 'Image Preview [Eclipse Nova]'];
const EDITOR_KEY = 'eclipseReviewPreview';
const controllers = new WeakMap();

export class PreviewState {
    constructor(raw, spec, editor = {}) {
        const config = typeof raw === 'string' ? JSON.parse(raw) : structuredClone(raw);
        if (!config || Array.isArray(config) || Object.keys(config).length !== 2
            || config.version !== 1 || typeof config.stop !== 'boolean') throw Error('Invalid preview configuration.');
        this.config = config; this.spec = spec; this.editor = { collapsed: editor.collapsed === true };
    }
    value() { return JSON.stringify(this.config); }
}

class PreviewForm {
    constructor(controller) {
        this.controller = controller;
        const { node, spec } = controller;
        if (spec.kind === 'image') {
            this.preview = createDOMPreview(node, { noWidget: true, freeResize: true, minHeight: 80 });
            this.image = node._eclipseDomPreview;
            this.preview.setAttribute('aria-label', 'Image preview');
            this.preview.style.height = '';
            this.preview.style.background = 'var(--en-input-bg)';
            this.image.img.alt = 'Preview image';
            // Both renderers allocate the available area; preserve the image aspect.
            this.image.img.style.width = '100%'; this.image.img.style.height = '100%';
            node.hideOutputImages = true;
        } else {
            this.text = createDOMTextController(node, { noWidget: true });
            this.preview = this.text.element;
            this.preview.style.height = '';
            this.text.textarea.setAttribute('aria-label', 'Text preview');
            this.text.textarea.style.background = 'var(--en-input-bg)';
            this.text.textarea.style.color = 'var(--en-text)';
            this.text.textarea.style.minHeight = '0';
            node._eclipseDomText = this.text;
            registerSubgraphDOMPreviewProvider(node, {
                name: DOM_TEXT_PREVIEW_NAME, kind: 'text', label: 'Text preview',
                createProjection(host, projection) {
                    const projected = createDOMTextController(host, { name: projection.name });
                    return { clear: projected.clear, dispose: projected.dispose, setValue: projected.setValue, widget: projected.widget };
                },
                getCurrentValue: this.text.getValue, readOutput: output => output?.text ?? [],
            });
        }
        this.preview.classList.add('en-review-preview-content');
    }
    render() {
        const { root, state } = this.controller;
        const focused = root.contains(document.activeElement) ? document.activeElement.getAttribute('aria-label') : null;
        const content = element('div', 'en-panel-content'), bar = element('div', 'en-panel-bar en-panel-with-run');
        const collapsed = state.editor.collapsed;
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Mode');
        const disclosure = button('', 'Mode', () => this.controller.edit(state => { state.editor.collapsed = !collapsed; }));
        disclosure.className = 'en-panel-disclosure'; disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Mode:'));
        if (collapsed) disclosure.append(element('span', 'en-panel-summary', state.config.stop ? 'Stop' : 'Stop off'));
        bar.append(disclosure);
        bar.append(runActions(this.controller, { stop: !collapsed }));
        content.append(bar, this.preview); root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[aria-label]')].find(item => item.getAttribute('aria-label') === focused)?.focus({ preventScroll: true });
    }
    executed(output) {
        if (this.text && output?.text) this.text.setValue(output.text);
        if (this.image && output?.images) feedDOMPreview(this.controller.node, output, { publish: false });
    }
    clearText() {
        this.text?.clear();
        publishSubgraphDOMPreview(this.controller.node, DOM_TEXT_PREVIEW_NAME, []);
    }
    dispose() {} // Restoring configuration must retain the current preview.
    destroy() {
        this.text?.dispose(); this.image?.dispose();
        if (this.controller.node._eclipseDomText === this.text) delete this.controller.node._eclipseDomText;
    }
}

function suppressNativePreview(node) {
    node.hideOutputImages = true; node.imgs = null; node.imageIndex = null;
    const graph = node.graph;
    const subgraph = graph?.isRootGraph === false || (graph?.rootGraph && graph.rootGraph !== graph);
    const key = subgraph && graph.id != null ? `${graph.id}:${node.id}` : String(node.id);
    const output = app.nodeOutputs?.[key];
    queueMicrotask(() => { if (output?.images) delete output.images; node.imgs = null; });
}

app.registerExtension({
    name: 'EclipseNova.ReviewPreviewPanels',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const image = inputData[1].editorSpec.kind === 'image';
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: PreviewState, Form: PreviewForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-review-preview', label: image ? 'Image Preview editor' : 'Show Any editor',
                fillHeight: true, minHeight: image ? 140 : 90,
                onDispose: node => { controllers.get(node)?.form.destroy(); controllers.delete(node); },
            });
            controllers.set(node, controller);
            return { widget: controller.widget, minWidth: 300, minHeight: image ? 330 : 220 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (!NODE_IDS.includes(data.name)) return;
        const configure = nodeType.prototype.onConfigure, added = nodeType.prototype.onAdded,
            executed = nodeType.prototype.onExecuted, connected = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configure?.apply(this, args), controller = controllers.get(this);
            if (controller) { controller.restore(controller.value()); controller.bindHost(); } return result;
        };
        nodeType.prototype.onAdded = function (...args) {
            const result = added?.apply(this, args); controllers.get(this)?.bindHost(); return result;
        };
        nodeType.prototype.onExecuted = function (output) {
            const controller = controllers.get(this);
            if (controller?.spec.kind !== 'image') {
                const result = executed?.apply(this, arguments); controller?.form.executed(output); return result;
            }
            // Leave the shared output message intact for exposed subgraph previews.
            const { images: _images, ...withoutImages } = output;
            const result = executed?.call(this, withoutImages);
            controller.form.executed(output); suppressNativePreview(this); return result;
        };
        nodeType.prototype.onConnectionsChange = function (type, slot, connectedNow, ...rest) {
            const result = connected?.call(this, type, slot, connectedNow, ...rest), controller = controllers.get(this);
            if (controller?.spec.kind === 'text' && type === 1 && slot === 0 && !connectedNow) controller.form.clearText();
            return result;
        };
    },
});
