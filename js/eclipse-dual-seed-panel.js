/** Dual Seed uses the same form and controls as Seed, with paired results. */
import { app, api } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { SeedForm } from './eclipse-seed-panel.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, DualSeedState, validPair } from './eclipse-dual-seed-state.js';
import { installDualSeedHooks } from './eclipse-dual-seed-queue.js';
const controllers = new WeakMap();
app.registerExtension({
    name: 'EclipseNova.DualSeedPanel',
    setup() { installDualSeedHooks(api, app, controllers); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: DualSeedState, Form: SeedForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-seed', label: 'Dual seed editor', onDispose: node => controllers.delete(node),
            });
            controller.widget.options.socketless = true;
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 420 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== NODE_ID) return;
        for (const method of ['onConfigure', 'onAdded']) {
            const original = nodeType.prototype[method];
            nodeType.prototype[method] = function (...args) {
                const result = original?.apply(this, args), controller = controllers.get(this);
                if (controller) { if (method === 'onConfigure') controller.restore(controller.value()); controller.bindHost(); }
                return result;
            };
        }
        const original = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function(output, ...args) {
            const result = original?.call(this, output, ...args), controller = controllers.get(this);
            if (controller && validPair(output?.eclipse_seed_pair)) controller.edit(state => state.record(output.eclipse_seed_pair));
            return result;
        };
    },
});
