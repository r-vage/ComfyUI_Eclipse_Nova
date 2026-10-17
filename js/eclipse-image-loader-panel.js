/** One serialized DOM widget per loader in classic canvas and Nodes 2.0. */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { IMAGE_ID, FILES_ID, IMAGE_WIDGET, FILES_WIDGET, EDITOR_KEY, LoaderState } from './eclipse-image-loader-state.js';
import { LoadImageForm } from './eclipse-load-image-form.js';
import { LoadFilesForm } from './eclipse-load-files-form.js';
import { stopAutomaticQueue } from './eclipse-queue-control-utils.js';

const controllers = new WeakMap();
app.registerExtension({
    name: 'EclipseNova.ImageLoaderPanels',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return Object.fromEntries([[IMAGE_WIDGET, LoadImageForm, 'en-load-image'], [FILES_WIDGET, LoadFilesForm, 'en-load-files']].map(([widgetType, Form, className]) =>
            [widgetType, (node, name, inputData) => {
                const controller = new ConfigurationPanel(node, name, inputData[1], {
                    State: LoaderState, Form, widgetType, editorKey: EDITOR_KEY, className, label: className === 'en-load-image' ? 'Load Image editor' : 'Load Files editor',
                    fillHeight: widgetType === IMAGE_WIDGET, minHeight: 220,
                    onDispose: node => { controllers.get(node)?.form.destroy(); controllers.delete(node); },
                });
                controllers.set(node, controller);
                return { widget: controller.widget, minWidth: 400, ...(widgetType === IMAGE_WIDGET ? { minHeight: 460 } : {}) };
            }]));
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (![IMAGE_ID, FILES_ID].includes(data.name)) return;
        const configure = nodeType.prototype.onConfigure, added = nodeType.prototype.onAdded,
            connected = nodeType.prototype.onConnectionsChange, executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configure?.apply(this, args), controller = controllers.get(this);
            if (controller) { controller.restore(controller.value()); controller.bindHost(); } return result;
        };
        nodeType.prototype.onAdded = function (...args) { const result = added?.apply(this, args); controllers.get(this)?.bindHost(); return result; };
        nodeType.prototype.onConnectionsChange = function (...args) {
            const result = connected?.apply(this, args), controller = controllers.get(this);
            if (args[0] === 1 && controller && !controller.invalid && !controller.disposed) controller.form.render(); return result;
        };
        nodeType.prototype.onExecuted = function (message) {
            const result = executed?.apply(this, arguments), controller = controllers.get(this);
            if (message?.eclipse_loader?.[0]) this._eclipseLoadFilesSelection = message.eclipse_loader[0];
            if (message?.eclipse_loader?.some(info => info.stopped)) stopAutomaticQueue();
            if (controller && !controller.invalid && !controller.disposed) controller.form.executed?.(message); return result;
        };
    },
});
