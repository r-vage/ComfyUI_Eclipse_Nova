/** Save Images-style mode bar, compact fields and pinned sections for prompt files. */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { EDITOR_KEY } from './eclipse-prompt-files-state.js';

export class PromptFilesForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); }
    get state() { return this.controller.state; }
    get info() { return this.state.editor.lastSelection ?? null; }
    set info(value) { this.state.editor.lastSelection = value; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    render() {
        this.menu.close();
        const root = this.controller.root, focused = root.contains(document.activeElement) ? document.activeElement?.dataset?.field : null;
        const content = element('div', 'en-panel-content');
        this.bar(content);
        if (this.state.config.options.save_to_disk !== false) {
            for (const [key, label] of Object.entries(this.state.spec.sections)) this.section(content, key, label);
        }
        root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    bar(parent) {
        const collapsed = this.state.editor.barCollapsed === true, bar = element('div', 'en-panel-bar');
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Mode');
        const toggle = button('', 'Mode', () => this.edit(state => { state.editor.barCollapsed = !collapsed; }));
        toggle.className = 'en-panel-disclosure'; toggle.dataset.field = 'mode'; toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Mode:'));
        const fields = this.state.spec.fields.filter(field => field.section === 'mode');
        if (collapsed) toggle.append(element('span', 'en-panel-summary', fields.filter(field => this.state.config.options[field.key]).map(field => field.label).join(' · ') || 'None'));
        bar.append(toggle);
        if (!collapsed) for (const field of fields) {
            const control = button(field.label, field.label, () => this.edit(state => { state.config.options[field.key] = !state.config.options[field.key]; }));
            control.title = field.tooltip; control.dataset.field = field.key;
            control.setAttribute('aria-pressed', String(this.state.config.options[field.key])); bar.append(control);
        }
        parent.append(bar);
    }
    section(parent, key, label) {
        const section = element('section', 'en-panel-section'), open = this.state.sectionOpen(key);
        section.setAttribute('aria-label', label);
        const header = element('div', 'en-panel-section-header');
        const toggle = button('', label, () => this.edit(state => state.toggleSection(key)));
        toggle.className = 'en-panel-section-toggle'; toggle.dataset.field = `section.${key}`; toggle.setAttribute('aria-expanded', String(open));
        const summary = element('span', 'en-panel-summary', this.state.summary(key)); summary.dataset.sectionSummary = key; summary.title = summary.textContent;
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} ${label}`), summary);
        const pin = button('⌖', `Pin ${label}`, () => this.edit(state => state.togglePin(key)));
        pin.dataset.field = `pin.${key}`; pin.setAttribute('aria-pressed', String(this.state.editor.pins?.[key] === true));
        header.append(toggle);
        if (key === 'files') {
            const refresh = button('↻', 'Refresh files', () => {
                this.info = null; this.controller.node._eclipseReadPromptSelection = null;
                this.edit(state => state.refresh());
            });
            refresh.dataset.field = 'refresh'; refresh.title = 'Reload files and restart selection on the next run. File edits are also detected automatically.';
            header.append(refresh);
        }
        header.append(pin); section.append(header);
        if (open) {
            const body = element('div', 'en-panel-section-body'), grid = element('div', 'en-panel-grid');
            for (const field of this.state.spec.fields) if (field.section === key && this.state.visible(field)) this.field(grid, field);
            body.append(grid);
            if (key === 'files') body.append(element('div', 'en-panel-note', 'One path per line, in prompt order. Blank prompt lines are ignored.'));
            if (key === 'selection') {
                const actions = element('div', 'en-panel-inline'); actions.style.marginTop = '7px';
                const last = button('🌘', 'Use last index', () => this.edit(state => {
                    state.config.options.index = this.info.index; state.config.options.advance = 'fixed';
                }));
                last.disabled = !this.info || this.info.stopped || !Number.isInteger(this.info.index);
                const reset = button('↶', 'Restart selection', () => {
                    this.info = null; this.controller.node._eclipseReadPromptSelection = null;
                    this.edit(state => state.refresh());
                });
                const status = element('span', 'en-panel-note', this.selectionText()); status.setAttribute('role', 'status');
                actions.append(reset, last, status); body.append(actions);
                body.append(element('div', 'en-panel-note', 'Index is the starting position. A connected seed freezes automatic selection until it changes.'));
            }
            if (key === 'output') body.append(element('div', 'en-panel-note', 'Pipe output_path and filename_prefix take priority. Source filepath/base_path are used for caption pairing.'));
            section.append(body);
        }
        parent.append(section);
    }
    field(parent, field) {
        const current = this.state.config.options[field.key];
        const set = (value, render = true) => this.edit(state => {
            if (state.spec.kind === 'read' && state.config.options[field.key] !== value) {
                state.editor.lastSelection = null; this.controller.node._eclipseReadPromptSelection = null;
            }
            state.config.options[field.key] = value;
        }, render);
        if (field.options) {
            const trigger = this.menu.field(parent, field.label, current, field.options, value => set(value));
            trigger.title = field.tooltip ?? current; trigger.dataset.field = field.key; return;
        }
        const label = element('label', 'en-panel-field'), input = element(field.multiline ? 'textarea' : 'input');
        input.dataset.field = field.key; input.setAttribute('aria-label', field.label); input.title = field.tooltip ?? field.label;
        input.value = current;
        if (field.multiline) { input.rows = 5; input.wrap = 'off'; label.style.gridColumn = '1 / -1'; }
        else input.type = typeof current === 'number' ? 'number' : 'text';
        if (field.min != null) { input.min = field.min; input.max = field.max; input.step = 1; }
        input.maxLength = field.maxLength ?? 4096;
        input.oninput = () => {
            if (!input.checkValidity() || (input.type === 'number' && !Number.isInteger(input.valueAsNumber))) return;
            set(input.type === 'number' ? input.valueAsNumber : input.value, false);
        };
        input.onchange = () => { input.value = this.state.config.options[field.key]; };
        label.append(element('span', '', field.label), input);
        if (field.wide) label.style.gridColumn = '1 / -1';
        parent.append(label);
    }
    selectionText() {
        if (!this.info) return 'No selection yet';
        if (this.info.stopped) return 'End reached — downstream execution blocked';
        const text = this.info.total ? `Last index: ${this.info.index} of ${this.info.total} prompts` : 'No readable prompts';
        return `${text}${this.info.missing?.length ? ` · ${this.info.missing.length} unreadable file(s)` : ''}`;
    }
    syncSummaries() {
        for (const item of this.controller.root.querySelectorAll('[data-section-summary]')) item.textContent = item.title = this.state.summary(item.dataset.sectionSummary);
        const status = this.controller.root.querySelector('[role="status"]'); if (status) status.textContent = this.selectionText();
        const last = this.controller.root.querySelector('[aria-label="Use last index"]');
        if (last) last.disabled = !this.info || this.info.stopped || !Number.isInteger(this.info.index);
    }
    executed(message) {
        const info = message?.eclipse_prompt_files?.[0];
        if (!info) return;
        this.info = JSON.parse(JSON.stringify(info));
        // Keep the last displayed index usable when a loaded workflow reuses a
        // cached execution. This is display state, separate from configuration.
        const node = this.controller.node; node.properties ??= {};
        node.properties[EDITOR_KEY] = JSON.parse(JSON.stringify(this.state.editor));
        this.syncSummaries();
    }
    dispose() { this.menu.close(); }
}
