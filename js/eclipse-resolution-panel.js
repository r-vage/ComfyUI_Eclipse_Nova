/** One resolution PIPE panel for both ComfyUI canvases. */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, ResolutionState } from './eclipse-resolution-state.js';
import { ResolutionForm } from './eclipse-resolution-form.js';

const controllers = new WeakMap();
app.registerExtension({
    name: 'EclipseNova.ResolutionPanel',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: ResolutionState, Form: ResolutionForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-resolution', label: 'Resolution settings', onDispose: node => controllers.delete(node),
            });
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 400 };
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
