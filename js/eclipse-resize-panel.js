/** Image Resize's structured panel and local socket-change notifications. */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, ResizeState } from './eclipse-resize-state.js';
import { ResizeForm } from './eclipse-resize-form.js';

const controllers = new WeakMap();
app.registerExtension({
    name: 'EclipseNova.ResizePanel',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: ResizeState, Form: ResizeForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-resize', label: 'Image Resize editor', onDispose: node => controllers.delete(node),
            });
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 380 };
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
            if (args[0] === 1 && ['width', 'height'].includes(this.inputs?.[args[1]]?.name) && controller && !controller.invalid && !controller.disposed) controller.form.render();
            return result;
        };
    },
});
