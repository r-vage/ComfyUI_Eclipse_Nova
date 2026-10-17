/** One FX DOM widget per node, shared by classic canvas and Nodes 2.0. */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { NODE_IDS, WIDGET_TYPE, EDITOR_KEY, FxState } from './eclipse-fx-state.js';
import { FxForm } from './eclipse-fx-form.js';

const controllers = new WeakMap();
app.registerExtension({
    name: 'EclipseNova.FxPanel',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: FxState, Form: FxForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-fx', label: `${inputData[1].editorSpec.kind === 'text' ? 'Text image' : 'Image'} FX editor`,
                onDispose: node => controllers.delete(node),
            });
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 400 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (!NODE_IDS.includes(data.name)) return;
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
            if (args[0] === 1 && ['mask', 'background_image', 'text_input'].includes(this.inputs?.[args[1]]?.name)
                && controller && !controller.invalid && !controller.disposed) controller.form.render();
            return result;
        };
    },
});
