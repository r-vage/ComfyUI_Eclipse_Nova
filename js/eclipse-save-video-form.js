/** Compact video-save controls using the common Nova design. */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { SECTIONS } from './eclipse-save-video-state.js';

export class SaveVideoForm {
    constructor(controller) {
        this.controller = controller; this.menu = new SearchMenu();
        this.controls = element('div', 'en-panel-content'); this.controls.style.flex = '0 0 auto';
    }
    get state() { return this.controller.state; }
    get source() { return this.controller.source(); }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    render() {
        this.menu.close();
        const root = this.controller.root, focused = root.contains(document.activeElement) ? document.activeElement?.dataset?.field : null;
        const content = element('div', 'en-panel-content');
        this.controls.replaceChildren(); this.bar(this.controls);
        for (const [key, label] of Object.entries(SECTIONS)) if (this.state.sectionVisible(key, this.source)) this.section(this.controls, key, label);
        content.append(this.controls);
        if (this.controller.preview) content.append(this.controller.preview);
        root.replaceChildren(content); this.controller.syncPreview();
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
        const active = field => this.state.config.options[field.key] && (field.key !== 'enable_trim' || this.state.canTrim(this.source));
        if (collapsed) toggle.append(element('span', 'en-panel-summary', fields.filter(active).map(field => field.label).join(' · ') || 'Save'));
        bar.append(toggle);
        if (!collapsed) for (const field of fields) {
            const control = button(field.label, field.label, () => this.edit(state => { state.config.options[field.key] = !state.config.options[field.key]; }));
            control.title = field.tooltip; control.dataset.field = field.key;
            control.disabled = field.key === 'enable_trim' && !this.state.canTrim(this.source);
            control.setAttribute('aria-pressed', String(active(field))); bar.append(control);
        }
        parent.append(bar);
    }
    section(parent, key, label) {
        const section = element('section', 'en-panel-section'), open = this.state.sectionOpen(key);
        section.setAttribute('aria-label', label);
        const header = element('div', 'en-panel-section-header');
        const toggle = button('', label, () => this.edit(state => state.toggleSection(key)));
        toggle.className = 'en-panel-section-toggle'; toggle.dataset.field = `section.${key}`; toggle.setAttribute('aria-expanded', String(open));
        const summary = element('span', 'en-panel-summary', this.state.summary(key, this.source)); summary.dataset.sectionSummary = key; summary.title = summary.textContent;
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} ${label}`), summary);
        const pin = button('⌖', `Pin ${label}`, () => this.edit(state => state.togglePin(key)));
        pin.dataset.field = `pin.${key}`; pin.setAttribute('aria-pressed', String(this.state.editor.pins?.[key] === true));
        header.append(toggle, pin); section.append(header);
        if (open) {
            const body = element('div', 'en-panel-section-body'), grid = element('div', 'en-panel-grid');
            for (const field of this.state.spec.fields) if (field.section === key && this.state.visible(field, this.source)) this.field(grid, field);
            body.append(grid);
            const notes = {
                output: 'Pipe output_path (or path) and filename_prefix take priority when present.',
                encoding: this.source === 'image' ? 'MP4 / H.264. Pipe fps takes priority over local FPS.'
                    : this.source === 'video' ? 'VIDEO keeps its dimensions, timing and soundtrack.' : 'Source timing sets frame cadence; local and pipe FPS are ignored.',
                trim: this.source === 'timeline' ? 'Exact timelines support duration trimming. Loop matching requires IMAGE frames.' : 'A single image with audio is held for the full audio duration.',
                metadata: 'Remove prompts affects generation parameters only. Embedded workflows and JSON keep their original text.',
            };
            body.append(element('div', 'en-panel-note', notes[key])); section.append(body);
        }
        parent.append(section);
    }
    field(parent, field) {
        const current = this.state.config.options[field.key];
        const set = (value, render = true) => this.edit(state => { state.config.options[field.key] = value; }, render);
        if (field.options) {
            const options = field.key === 'trim_mode' && this.source === 'timeline' ? field.options.filter(value => !value.startsWith('loop_')) : field.options;
            const trigger = this.menu.field(parent, field.label, current, options, value => set(value));
            trigger.dataset.field = field.key; trigger.title = field.tooltip ?? field.label; return;
        }
        const boolean = typeof current === 'boolean', label = element('label', boolean ? 'en-panel-inline' : 'en-panel-field');
        const input = element('input'); input.dataset.field = field.key; input.setAttribute('aria-label', field.label); input.title = field.tooltip ?? field.label;
        if (boolean) {
            input.type = 'checkbox'; input.checked = current; input.onchange = () => set(input.checked);
            label.append(input, element('span', '', field.label));
        } else {
            input.type = typeof current === 'number' ? 'number' : 'text'; input.value = current;
            if (field.min != null) { input.min = field.min; input.max = field.max; input.step = field.step; }
            if (field.maxLength) input.maxLength = field.maxLength;
            input.oninput = () => {
                if (!input.checkValidity() || (input.type === 'number' && !Number.isFinite(input.valueAsNumber))) return;
                set(input.type === 'number' ? input.valueAsNumber : input.value, false);
            };
            input.onchange = () => { input.value = this.state.config.options[field.key]; };
            label.append(element('span', '', field.label), input);
            if (field.section === 'output') label.style.gridColumn = '1 / -1';
        }
        label.title = field.tooltip ?? ''; parent.append(label);
    }
    syncSummaries() {
        for (const item of this.controller.root.querySelectorAll('[data-section-summary]')) item.textContent = item.title = this.state.summary(item.dataset.sectionSummary, this.source);
    }
    dispose() { this.menu.close(); }
}
