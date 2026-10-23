/** Manual image timeline host for both renderers. Copyright (c) 2026 r-vage. Apache-2.0. */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { isConfiguringGraph } from './eclipse-widget-utils.js';
import { ImageTimelineState, ID, WIDGET, EDITOR } from './eclipse-image-timeline-state.js';
import { ImageTimelineForm } from './eclipse-image-timeline-form.js';

const controllers = new WeakMap();
app.registerExtension({
    name: 'EclipseNova.ImageTimelineLoader',
    setup() {
        ensurePanelStyle();
        if (!document.getElementById('eclipse-image-timeline-style')) {
            const link = document.createElement('link'); link.id = 'eclipse-image-timeline-style'; link.rel = 'stylesheet';
            link.href = new URL('./eclipse-image-timeline.css', import.meta.url).href; document.head.append(link);
        }
    },
    getCustomWidgets() {
        return { [WIDGET]: (node, name, inputData) => {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: ImageTimelineState, Form: ImageTimelineForm, widgetType: WIDGET, editorKey: EDITOR,
                className: 'en-image-timeline', label: 'Load Image Timeline editor', fillHeight: true, minHeight: 320,
                onDispose: node => { controllers.get(node)?.form.destroy(); controllers.delete(node); },
            });
            controller.widget.options.socketless = true; controllers.set(node, controller);
            return { widget: controller.widget, minWidth: 640, minHeight: 400 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== ID) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args); if (!isConfiguringGraph()) this.setSize([860, 600]); return result;
        };
        for (const name of ['onAdded', 'onConfigure', 'onGraphConfigured', 'onConnectionsChange']) {
            const previous = nodeType.prototype[name];
            nodeType.prototype[name] = function (...args) {
                const result = previous?.apply(this, args), controller = controllers.get(this);
                if (controller) {
                    if (name === 'onConfigure') controller.restore(controller.value());
                    else if (!controller.invalid) controller.form.render();
                    controller.bindHost();
                }
                return result;
            };
        }
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (output) {
            const result = executed?.apply(this, arguments); controllers.get(this)?.form.executed(output); return result;
        };
    },
});
