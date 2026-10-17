/** SPDX-License-Identifier: Apache-2.0
 * One structured widget per new media tool, shared by classic and Nodes 2.0.
 */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { EDITOR_KEY, NODE_IDS, WIDGET_TYPE, MediaToolState } from './eclipse-media-tool-state.js';
import { MediaToolForm } from './eclipse-media-tool-form.js';
import { RecorderSession, installRecorderQueueHooks } from './eclipse-recorder-session.js';

const controllers = new WeakMap();
app.registerExtension({
    name: 'EclipseNova.MediaToolPanels',
    setup() { ensurePanelStyle(); installRecorderQueueHooks(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: MediaToolState, Form: MediaToolForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-media-tool', label: `${inputData[1].editorSpec.title} editor`,
                onDispose: () => { controller.recorder?.dispose(); controllers.delete(node); },
            });
            if (controller.spec.kind === 'recorder') { controller.recorder = new RecorderSession(controller); controller.form.syncRecorder(); }
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 380 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (!NODE_IDS.includes(data.name)) return;
        const configure = nodeType.prototype.onConfigure, added = nodeType.prototype.onAdded, connection = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configure?.apply(this, args), controller = controllers.get(this);
            if (controller) { controller.restore(controller.value()); controller.bindHost(); controller.recorder?.scheduleRestore(); } return result;
        };
        nodeType.prototype.onAdded = function (...args) {
            const result = added?.apply(this, args), controller = controllers.get(this);
            controller?.bindHost(); controller?.recorder?.scheduleRestore(); return result;
        };
        nodeType.prototype.onConnectionsChange = function (...args) {
            const result = connection?.apply(this, args), controller = controllers.get(this);
            if (args[0] === 1 && ['target_width', 'target_height'].includes(this.inputs?.[args[1]]?.name) && controller && !controller.invalid) controller.form.syncSummaries();
            return result;
        };
    },
});
