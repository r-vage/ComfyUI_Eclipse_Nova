/** Eclipse Nova: one adjustments editor shared by classic and Nodes 2.0. */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, AdjustmentsState } from './eclipse-adjustments-state.js';
import { AdjustmentsForm } from './eclipse-adjustments-form.js';

const controllers = new WeakMap();
app.registerExtension({
    name: 'EclipseNova.ImageAdjustments',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: AdjustmentsState, Form: AdjustmentsForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-adjustments', label: 'Image adjustments editor', onDispose: node => controllers.delete(node),
            });
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 400 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== NODE_ID) return;
        const configure = nodeType.prototype.onConfigure, added = nodeType.prototype.onAdded, connection = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configure?.apply(this, args), controller = controllers.get(this);
            if (controller) { controller.restore(controller.value()); controller.bindHost(); } return result;
        };
        nodeType.prototype.onAdded = function (...args) {
            const result = added?.apply(this, args); controllers.get(this)?.bindHost(); return result;
        };
        nodeType.prototype.onConnectionsChange = function (...args) {
            const result = connection?.apply(this, args), controller = controllers.get(this);
            if (args[0] === 1 && ['image_ref', 'upscale_by'].includes(this.inputs?.[args[1]]?.name)
                && controller && !controller.invalid && !controller.disposed) controller.form.render();
            return result;
        };
    },
});
