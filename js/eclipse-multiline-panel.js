/** Resizable multiline editor using the shared Nova theme in both canvases. */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { element, button, ensurePanelStyle } from './eclipse-panel-controls.js';
import { TextFieldSizes } from './eclipse-panel-text-layout.js';
import { runActions } from './eclipse-panel-run.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, MultilineState } from './eclipse-multiline-state.js';

const controllers = new WeakMap();

class MultilineForm {
    constructor(controller) {
        this.controller = controller;
        this.text = element('textarea'); this.text.setAttribute('aria-label', 'Text');
        this.text.spellcheck = false; this.text.maxLength = controller.spec.maxTextLength;
        this.text.oninput = () => controller.edit(state => state.setText(this.text.value), false);
        this.text.rows = 6;
        this.result = element('textarea'); this.result.setAttribute('aria-label', 'Result');
        this.result.readOnly = true; this.result.rows = 6;
        // One 18px line plus the shared textarea padding and borders.
        this.sizes = new TextFieldSizes(controller, { bounded: true, minHeight: 34 });
    }
    render() {
        this.sizes.disconnect();
        const { root, state } = this.controller, { collapsed, wrap } = state.editor;
        const filtering = state.config.filter === true;
        const active = root.contains(document.activeElement) ? document.activeElement : null;
        const focused = active?.getAttribute('aria-label');
        const selection = active?.tagName === 'TEXTAREA' ? [active.selectionStart, active.selectionEnd, active.selectionDirection] : null;
        const scroll = [this.text, this.result].map(input => [input.scrollTop, input.scrollLeft]);
        const content = element('div', 'en-panel-content en-panel-text-layout'), bar = element('div', 'en-panel-bar en-panel-with-run');
        const showResult = state.config.preview === true && state.editor.resultOpen !== false;
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Options');
        const disclosure = button('', 'Options', () => this.controller.edit(state => { state.editor.collapsed = !state.editor.collapsed; }));
        disclosure.className = 'en-panel-disclosure'; disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Options:'));
        if (collapsed) disclosure.append(element('span', 'en-panel-summary', [wrap ? 'Wrap' : 'Wrap off', `Filter ${filtering ? 'on' : 'off'}`, state.config.preview ? 'Preview' : '', state.config.stop ? 'Stop' : 'Stop off'].filter(Boolean).join(' · ')));
        bar.append(disclosure);
        if (!collapsed) {
            const toggle = button('Wrap', 'Wrap long lines', () => this.controller.edit(state => { state.editor.wrap = !state.editor.wrap; }));
            toggle.title = 'Wrap long lines visually. Text and list items stay unchanged.';
            toggle.setAttribute('aria-pressed', String(wrap)); bar.append(toggle);
            const filter = button('Filter', 'Filter prompt', () => this.controller.edit(state => { state.config.filter = !state.config.filter; }));
            filter.title = 'Use the editor text as comma/newline-separated removal patterns for input_string. Matches ignore case; spaces and underscores are equivalent. Each * matches one word. Off keeps the normal text/prefix behavior.';
            filter.setAttribute('aria-pressed', String(filtering)); bar.append(filter);
            for (const [key, label, title] of [
                ['preview', 'Preview', 'Show the Result section. Local text updates immediately; connected inputs update when the workflow runs.'],
            ]) {
                const control = button(label, label, () => this.controller.edit(state => { state.config[key] = !state.config[key]; }));
                control.title = title; control.setAttribute('aria-pressed', String(state.config[key] === true)); bar.append(control);
            }
        }
        bar.append(runActions(this.controller, { stop: !collapsed, beforeRun: () => {
            if (!state.config.preview || state.editor.resultOpen === false) this.controller.edit(state => {
                state.config.preview = true; state.editor.resultOpen = true;
            });
        } }));
        this.text.placeholder = filtering ? 'Enter removal patterns, separated by commas or newlines…' : 'Enter text…';
        this.text.title = filtering ? 'Filter patterns for the connected input_string. Example: *hair removes long hair or long_hair. Both outputs contain the filtered prompt.' : 'Text to output, with an optional connected prefix.';
        this.text.wrap = wrap ? 'soft' : 'off';
        this.result.wrap = this.text.wrap;
        if (this.text.value !== state.config.text) this.text.value = state.config.text;
        this.sizes.attach(this.text, 'text');
        const field = element('div'); field.dataset.textSection = 'text'; field.append(this.text);
        content.append(bar, field);
        if (state.config.preview) {
            const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', 'Result'); section.dataset.textSection = 'result';
            const toggle = button('', 'Result', () => this.controller.edit(state => { state.editor.resultOpen = !showResult; }));
            toggle.className = 'en-panel-section-toggle'; toggle.setAttribute('aria-expanded', String(showResult));
            toggle.append(element('span', 'en-panel-section-label', `${showResult ? '▾' : '▸'} Result`));
            section.append(toggle);
            if (showResult) {
                const body = element('div', 'en-panel-section-body');
                this.sizes.attach(this.result, 'result');
                const note = element('div', 'en-panel-note'); note.setAttribute('role', 'status');
                body.append(this.result, note); section.append(body);
            }
            content.append(section);
        }
        this.sizes.layout(content);
        root.replaceChildren(content); this.syncSummaries();
        if (active?.isConnected) active.focus({ preventScroll: true });
        else if (focused) [...root.querySelectorAll('[aria-label]')].find(item => item.getAttribute('aria-label') === focused)?.focus({ preventScroll: true });
        if (selection && active.isConnected) active.setSelectionRange(...selection);
        [this.text, this.result].forEach((input, index) => { [input.scrollTop, input.scrollLeft] = scroll[index]; });
    }
    connected() { return this.controller.node.inputs?.some(input => input.name === 'input_string' && input.link != null) === true; }
    syncSummaries() {
        // Update the result in place, preserving text height, selection and scroll.
        const state = this.controller.state;
        if (!state.config.preview || state.editor.resultOpen === false) return;
        const connected = this.connected(), value = state.result(connected);
        if (this.result.value !== value) this.result.value = value;
        const note = this.controller.root.querySelector('[role="status"]');
        if (note) note.textContent = connected
            ? state.editor.preview ? 'Last run · connected inputs update when the workflow runs.' : 'Run the workflow to preview connected input.'
            : state.config.filter ? 'Connect input_string to filter a prompt.' : 'Preview of the full string output.';
    }
    executed(output) {
        const results = output?.eclipse_multiline;
        if (!Array.isArray(results) || this.controller.disposed || this.controller.invalid) return;
        this.controller.state.editor.preview = { text: results.map(item => item.text).join('\n') };
        const { node, state } = this.controller;
        node.properties ??= {}; node.properties[EDITOR_KEY] = structuredClone(state.editor);
        this.syncSummaries(); node.setDirtyCanvas(true, true);
    }
    dispose() { this.sizes.disconnect(); } // The same textareas survive restoration.
    destroy() { this.text.oninput = null; }
}

app.registerExtension({
    name: 'EclipseNova.MultilinePanel',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: MultilineState, Form: MultilineForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-multiline', label: 'String Multiline editor', fillHeight: true, minHeight: 82,
                onDispose: node => { controllers.get(node)?.form.destroy(); controllers.delete(node); },
            });
            controller.widget.options.socketless = true;
            controllers.set(node, controller);
            return { widget: controller.widget, minWidth: 360, minHeight: 270 };
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
                    controller.form.syncSummaries();
                }
                return result;
            };
        }
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (output, ...args) {
            const result = executed?.call(this, output, ...args); controllers.get(this)?.form.executed(output); return result;
        };
    },
});
