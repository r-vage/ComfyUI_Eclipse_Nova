/** One DOM configuration widget per prompt-file node, in both ComfyUI renderers. */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { stopAutomaticQueue } from './eclipse-queue-control-utils.js';
import { READ_ID, SAVE_ID, READ_WIDGET, SAVE_WIDGET, EDITOR_KEY, PromptFilesState } from './eclipse-prompt-files-state.js';
import { PromptFilesForm } from './eclipse-prompt-files-form.js';

const controllers = new WeakMap();
app.registerExtension({
    name: 'EclipseNova.PromptFilesPanels',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return Object.fromEntries([[READ_WIDGET, 'en-read-prompt-files', 'Read Prompt Files editor'], [SAVE_WIDGET, 'en-save-prompt', 'Save Prompt editor']].map(([widgetType, className, label]) =>
            [widgetType, (node, name, inputData) => {
                const controller = new ConfigurationPanel(node, name, inputData[1], {
                    State: PromptFilesState, Form: PromptFilesForm, widgetType, editorKey: EDITOR_KEY, className, label,
                    onDispose: node => controllers.delete(node),
                });
                controller.widget.options.socketless = true; controllers.set(node, controller);
                return { widget: controller.widget, minWidth: 380 };
            }]));
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (![READ_ID, SAVE_ID].includes(data.name)) return;
        for (const method of ['onConfigure', 'onAdded', 'onGraphConfigured']) {
            const original = nodeType.prototype[method];
            nodeType.prototype[method] = function (...args) {
                const result = original?.apply(this, args), controller = controllers.get(this);
                if (controller) {
                    if (method === 'onConfigure') {
                        controller.restore(controller.value());
                        if (!controller.invalid && data.name === READ_ID) this._eclipseReadPromptSelection = controller.state.editor.lastSelection ?? null;
                    }
                    controller.bindHost();
                }
                return result;
            };
        }
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const result = executed?.apply(this, arguments), controller = controllers.get(this);
            if (message?.eclipse_prompt_files?.[0]) this._eclipseReadPromptSelection = message.eclipse_prompt_files[0];
            if (message?.eclipse_prompt_files?.some(info => info.stopped)) stopAutomaticQueue();
            if (controller && !controller.invalid && !controller.disposed) controller.form.executed(message);
            return result;
        };
    },
});
