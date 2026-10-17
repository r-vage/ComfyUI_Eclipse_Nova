/** Smart Folder's single DOM panel owns execution state in both ComfyUI renderers. */
import { app, api } from './comfy/index.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, FolderState } from './eclipse-smart-folder-v2-state.js';
import { FolderForm } from './eclipse-smart-folder-v2-form.js';
import { installQueueHook } from './eclipse-smart-folder-v2-queue.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { validSeed } from './eclipse-panel-seed.js';

const controllers = new WeakMap();
export class FolderController extends ConfigurationPanel {
    constructor(node, name, options) {
        super(node, name, options, {
            State: FolderState, Form: FolderForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
            className: 'en-folder', label: 'Smart Folder settings', onDispose: node => controllers.delete(node),
        });
    }
}

app.registerExtension({
    name: 'EclipseNova.SmartFolderPanel',
    setup() { ensurePanelStyle(); installQueueHook(api, app, controllers); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new FolderController(node, name, inputData[1]); controllers.set(node, controller);
            return { widget: controller.widget, minWidth: 400 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== NODE_ID) return;
        const configure = nodeType.prototype.onConfigure, added = nodeType.prototype.onAdded, executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configure?.apply(this, args), controller = controllers.get(this);
            if (controller) { controller.restore(controller.value()); controller.bindHost(); } return result;
        };
        nodeType.prototype.onAdded = function (...args) {
            const result = added?.apply(this, args); controllers.get(this)?.bindHost(); return result;
        };
        nodeType.prototype.onExecuted = function (output, ...args) {
            const result = executed?.call(this, output, ...args), controller = controllers.get(this);
            controller?.edit(state => {
                if (typeof output?.eclipse_folder?.[0] === 'string') state.editor.lastPath = output.eclipse_folder[0];
                if (validSeed(output?.eclipse_seed?.[0])) state.editor.lastSeed = output.eclipse_seed[0];
            });
            return result;
        };
    },
});
