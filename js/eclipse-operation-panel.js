/** SPDX-License-Identifier: Apache-2.0
 * One themed configuration widget per redesigned fixed-input operation.
 */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { EDITOR_KEY, WIDGET_TYPE, OperationState } from './eclipse-operation-state.js';
import { OperationForm } from './eclipse-operation-form.js';

const controllers = new WeakMap();
app.registerExtension({
    name: 'EclipseNova.OperationPanels',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const spec = inputData[1].editorSpec, fillHeight = !!(spec.layout.preview || spec.layout.annotation);
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: OperationState, Form: OperationForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-operation', label: `${spec.title} editor`, fillHeight, minHeight: 100,
                onDispose: node => { controllers.get(node)?.form.destroy(); controllers.delete(node); },
            });
            controllers.set(node, controller);
            return { widget: controller.widget, minWidth: 320, ...(fillHeight ? { minHeight: 300 } : {}) };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        const spec = data.input?.required?.configuration?.[1]?.editorSpec;
        if (spec?.family !== 'operation') return;
        if (spec.layout.annotation) nodeType.prototype.isVirtualNode = true;
        const configure = nodeType.prototype.onConfigure, added = nodeType.prototype.onAdded,
            connected = nodeType.prototype.onConnectionsChange, executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configure?.apply(this, args), controller = controllers.get(this);
            if (controller) { controller.restore(controller.value()); controller.bindHost(); } return result;
        };
        nodeType.prototype.onAdded = function (...args) {
            const result = added?.apply(this, args); controllers.get(this)?.bindHost(); return result;
        };
        nodeType.prototype.onConnectionsChange = function (...args) {
            const result = connected?.apply(this, args), controller = controllers.get(this);
            if (args[0] === 1 && controller && !controller.invalid) controller.form.render();
            return result;
        };
        nodeType.prototype.onExecuted = function (output) {
            const controller = controllers.get(this);
            if (!spec.layout.preview) { const result = executed?.apply(this, arguments); controller?.form.executed(output); return result; }
            const { images: _images, ...withoutImages } = output;
            const result = executed?.call(this, withoutImages); controller?.form.executed(output);
            this.hideOutputImages = true; this.imgs = null; this.imageIndex = null;
            const graph = this.graph, subgraph = graph?.isRootGraph === false || (graph?.rootGraph && graph.rootGraph !== graph);
            const key = subgraph && graph.id != null ? `${graph.id}:${this.id}` : String(this.id), cached = app.nodeOutputs?.[key];
            queueMicrotask(() => { if (cached?.images) delete cached.images; this.imgs = null; });
            return result;
        };
    },
});
