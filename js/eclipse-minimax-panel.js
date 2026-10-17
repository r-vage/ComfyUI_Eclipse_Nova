/** SPDX-License-Identifier: Apache-2.0
 * Three segmented MiniMax panels share the native DOM configuration lifecycle in both canvases.
 */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { MiniMaxState, NODE_IDS, WIDGET_TYPE, EDITOR_KEY } from './eclipse-minimax-state.js';
import { MiniMaxForm } from './eclipse-minimax-form.js';

const controllers = new WeakMap();
app.registerExtension({
    name: 'EclipseNova.MiniMaxH3Panels',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: MiniMaxState, Form: MiniMaxForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-minimax', label: `${inputData[1].editorSpec.title} editor`, onDispose: node => controllers.delete(node),
            });
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 420 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (!NODE_IDS.includes(data.name)) return;
        for (const method of ['onConfigure', 'onAdded', 'onGraphConfigured', 'onConnectionsChange']) {
            const original = nodeType.prototype[method];
            nodeType.prototype[method] = function (...args) {
                const result = original?.apply(this, args), controller = controllers.get(this);
                if (controller && !controller.disposed) {
                    if (method === 'onConfigure') controller.restore(controller.value());
                    controller.bindHost();
                    if (method === 'onGraphConfigured' || (method === 'onConnectionsChange' && args[0] === 1)) controller.form.render();
                }
                return result;
            };
        }
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message, ...args) {
            const result = executed?.call(this, message, ...args), controller = controllers.get(this);
            if (controller && typeof message?.eclipse_minimax_report?.[0] === 'string') {
                controller.edit(state => { state.editor.lastReport = message.eclipse_minimax_report[0]; });
            }
            return result;
        };
    },
});
