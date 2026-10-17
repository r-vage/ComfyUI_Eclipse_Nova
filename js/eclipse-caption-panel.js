/** One caption widget for standard canvas and Nodes 2.0.
 * Copyright (c) 2026 r-vage. MIT License.
 */
import { app, api } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { installSeedQueueHook } from './eclipse-panel-seed-queue.js';
import { validSeed } from './eclipse-panel-seed.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, CaptionState } from './eclipse-caption-state.js';
import { CaptionForm } from './eclipse-caption-form.js';

const controllers = new WeakMap();
app.registerExtension({
    name: 'EclipseNova.LyricCaptionsPanel',
    setup() { ensurePanelStyle(); installSeedQueueHook(api, app, controllers, { nodeId: NODE_ID, editorKey: EDITOR_KEY }); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: CaptionState, Form: CaptionForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-captions', label: 'Lyric captions editor', onDispose: node => controllers.delete(node),
            });
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 440 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== NODE_ID) return;
        for (const method of ['onConfigure', 'onAdded', 'onConnectionsChange']) {
            const original = nodeType.prototype[method];
            nodeType.prototype[method] = function (...args) {
                const result = original?.apply(this, args), controller = controllers.get(this);
                if (controller && !controller.disposed) {
                    if (method === 'onConfigure') controller.restore(controller.value());
                    controller.bindHost();
                    if (method === 'onConnectionsChange' && args[0] === 1 && !controller.invalid
                        && ['width', 'height', 'fps', 'background', 'corrected_timing'].includes(this.inputs?.[args[1]]?.name)) controller.form.render();
                }
                return result;
            };
        }
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (output, ...args) {
            const result = executed?.call(this, output, ...args), controller = controllers.get(this);
            if (controller && validSeed(output?.eclipse_seed?.[0])) controller.edit(state => { state.editor.lastSeed = output.eclipse_seed[0]; });
            return result;
        };
    },
});
