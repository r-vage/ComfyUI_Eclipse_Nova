/** One serialized Prompt Forge editor for standard canvas and Nodes 2.0. */
import { app, api } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { validSeed } from './eclipse-panel-seed.js';
import { installSeedQueueHook } from './eclipse-panel-seed-queue.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, ForgeState } from './eclipse-forge-state.js';
import { ForgeForm } from './eclipse-forge-form.js';

const controllers = new WeakMap();
class ForgePanel extends ConfigurationPanel {
    connected() { return this.node.inputs?.some(input => input.name === 'seed_input' && input.link != null); }
    syncConnection(restored = false) {
        if (this.disposed || this.invalid || !this.node.graph || (app.configuringGraph && !restored)) return;
        if (!this.connected() && this.state.config.seed.source === 'input') this.edit(state => state.setLocalSeed(true, false));
        else this.form.render();
    }
}

app.registerExtension({
    name: 'EclipseNova.PromptForgePanel',
    setup() { ensurePanelStyle(); installSeedQueueHook(api, app, controllers, { nodeId: NODE_ID, editorKey: EDITOR_KEY }); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ForgePanel(node, name, inputData[1], {
                State: ForgeState, Form: ForgeForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-forge', label: 'Prompt Forge editor', onDispose: node => controllers.delete(node),
                fillHeight: true, minHeight: 200,
            });
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 430, minHeight: 450 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== NODE_ID) return;
        for (const method of ['onConfigure', 'onAdded', 'onGraphConfigured', 'onConnectionsChange']) {
            const original = nodeType.prototype[method];
            nodeType.prototype[method] = function (...args) {
                const result = original?.apply(this, args), controller = controllers.get(this);
                if (controller) {
                    if (method === 'onConfigure') controller.restore(controller.value());
                    controller.bindHost();
                    if (method !== 'onConfigure') controller.syncConnection(method === 'onGraphConfigured');
                }
                return result;
            };
        }
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (output, ...args) {
            const result = executed?.call(this, output, ...args), controller = controllers.get(this);
            if (controller && (validSeed(output?.eclipse_seed?.[0]) || Array.isArray(output?.eclipse_forge))) controller.edit(state => {
                if (validSeed(output?.eclipse_seed?.[0])) state.editor.lastSeed = output.eclipse_seed[0];
                if (Array.isArray(output?.eclipse_forge)) state.editor.lastResult = output.eclipse_forge.join('\n');
            }, false);
            return result;
        };
    },
});
