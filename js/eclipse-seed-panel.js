/** The standalone Seed node, using the shared Nova design in both renderers. */
import { app, api } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { element, button, ensurePanelStyle } from './eclipse-panel-controls.js';
import { seedControls } from './eclipse-panel-seed-controls.js';
import { validSeed } from './eclipse-panel-seed.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, StandaloneSeedState } from './eclipse-seed-state.js';
import { installStandaloneSeedHooks, resolveNodeSeed } from './eclipse-seed-queue.js';

const controllers = new WeakMap();
export class SeedForm {
    constructor(controller) { this.controller = controller; }
    render() {
        const { root, state } = this.controller;
        const focus = root.contains(document.activeElement) ? document.activeElement.getAttribute('aria-label') ?? document.activeElement.dataset.field : null;
        const edit = fn => this.controller.edit(fn), content = element('div', 'en-panel-content');
        const bar = element('div', 'en-panel-bar'), collapsed = state.editor.barCollapsed;
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Mode');
        const disclosure = button('', 'Mode', () => edit(state => { state.editor.barCollapsed = !collapsed; }));
        disclosure.className = 'en-panel-disclosure'; disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Mode:'));
        if (collapsed) disclosure.append(element('span', 'en-panel-summary', `${state.config.bits}-bit`));
        bar.append(disclosure);
        if (!collapsed) {
            const bits = button('64-bit', '64-bit', () => edit(state => state.toggleBits()));
            bits.setAttribute('aria-pressed', String(state.config.bits === 64));
            bits.title = 'Enabled: unsigned 64-bit seeds. Disabled: unsigned 32-bit seeds. Switching to 32-bit keeps the lower 32 bits.';
            bar.append(bits);
        }
        content.append(bar);
        if (state.config.seeds) {
            for (const key of ['image', 'prompt']) {
                const controller = this.controller;
                seedControls(content, {
                    state: state.channel(key),
                    edit: (fn, render = true) => controller.edit(state => fn(state.channel(key)), render),
                }, key === 'image' ? 'Image' : 'Prompt');
            }
        } else seedControls(content, this.controller);
        const historyLabel = value => state.historyLabel ? state.historyLabel(value) : value;
        const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', 'Results');
        const header = element('div', 'en-panel-section-header'), open = state.editor.resultsOpen;
        const toggle = button('', 'Results', () => edit(state => { state.editor.resultsOpen = !open; }));
        toggle.className = 'en-panel-section-toggle'; toggle.setAttribute('aria-expanded', String(open));
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} Results`),
            element('span', 'en-panel-summary', state.editor.history.length ? historyLabel(state.editor.history[0]) : 'No seeds used yet'));
        const clear = button('↺', 'Clear seed history', () => edit(state => { state.editor.history = []; }));
        clear.disabled = !state.editor.history.length; header.append(toggle, clear); section.append(header);
        if (open) {
            const list = element('div', 'en-seed-history'); list.setAttribute('role', 'list'); list.setAttribute('aria-label', 'Recently used seeds');
            list.addEventListener('wheel', event => event.stopPropagation(), { passive: true });
            for (const value of state.editor.history) {
                const row = element('div'); row.setAttribute('role', 'listitem');
                const use = button(historyLabel(value), `Use seed ${historyLabel(value)}`, () => edit(state => state.reuse(value)));
                use.title = state.validSeed(value) ? `Use seed ${historyLabel(value)}` : `Use seed ${historyLabel(value)} in 64-bit mode`;
                row.append(use); list.append(row);
            }
            if (!state.editor.history.length) list.append(element('div', 'en-panel-note', 'Used seeds appear here after execution.'));
            section.append(list);
        }
        content.append(section); root.replaceChildren(content);
        if (focus) [...root.querySelectorAll('[aria-label], [data-field]')].find(item => (item.getAttribute('aria-label') ?? item.dataset.field) === focus)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    syncSummaries() {}
    dispose() {}
}

app.registerExtension({
    name: 'EclipseNova.SeedPanel',
    setup() { ensurePanelStyle(); installStandaloneSeedHooks(api, app, controllers); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: StandaloneSeedState, Form: SeedForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-seed', label: 'Seed editor', onDispose: node => controllers.delete(node),
            });
            controller.widget.options.socketless = true;
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 380 };
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
        // Wildcard consumers ask the producer for its queue seed.
        nodeType.prototype.getSeedToUse = function () { return resolveNodeSeed(controllers.get(this)); };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (output, ...args) {
            const result = executed?.call(this, output, ...args), controller = controllers.get(this), seed = output?.eclipse_seed?.[0];
            if (controller && validSeed(seed)) controller.edit(state => state.record(seed));
            return result;
        };
    },
});
