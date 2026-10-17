/** Prompt Forge's mode bar and text/seed sections on the shared Nova surface. */
import { element, button } from './eclipse-panel-controls.js';
import { seedControls } from './eclipse-panel-seed-controls.js';
import { runActions } from './eclipse-panel-run.js';
import { TextFieldSizes } from './eclipse-panel-text-layout.js';

export class ForgeForm {
    constructor(controller) { this.controller = controller; this.textSizes = new TextFieldSizes(controller, { bounded: true }); }
    get state() { return this.controller.state; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    render() {
        this.textSizes.disconnect();
        const { root } = this.controller;
        const focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        const content = element('div', 'en-panel-content en-panel-text-layout');
        this.bar(content);
        if (!this.state.spec.ratings.some(key => this.state.enabled(key))) {
            const note = element('div', 'en-panel-error', 'Select at least one content-rating pool in Mode.');
            note.setAttribute('role', 'status'); content.append(note);
        }
        for (const field of this.state.spec.texts) {
            if (field.key === 'exclude_tag_categories' && !this.state.enabled('categories')) continue;
            this.section(content, field.key, field.label, parent => {
                const input = element('textarea'); input.rows = 3; input.maxLength = this.state.spec.maxText;
                input.setAttribute('aria-label', field.label); input.title = field.tooltip; input.dataset.field = `texts.${field.key}`;
                input.value = this.state.config.texts[field.key];
                this.textSizes.attach(input, field.key);
                input.oninput = () => this.edit(state => { state.config.texts[field.key] = input.value; }, false);
                parent.append(input);
            });
        }
        this.section(content, 'result', 'Result', parent => {
            const output = element('textarea'); output.rows = 4; output.readOnly = true;
            output.setAttribute('aria-label', 'Result'); output.dataset.field = 'result';
            output.value = this.state.editor.lastResult ?? ''; this.textSizes.attach(output, 'result');
            parent.append(output);
        });
        if (this.state.config.seed.source === 'local') this.section(content, 'seed', 'Seed', body => seedControls(body, this.controller));
        this.textSizes.layout(content);
        root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    bar(parent) {
        const collapsed = this.state.editor.barCollapsed === true, bar = element('div', 'en-panel-bar en-panel-with-run');
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Mode');
        const toggle = button('', 'Mode', () => this.edit(state => { state.editor.barCollapsed = !collapsed; }));
        toggle.className = 'en-panel-disclosure'; toggle.dataset.field = 'mode'; toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Mode:'));
        const local = this.state.config.seed.source === 'local';
        if (collapsed) {
            const summary = element('span', 'en-panel-summary', [
                ...this.state.spec.features.filter(field => this.state.enabled(field.key)).map(field => field.label),
                local ? 'Local seed' : 'Input seed',
            ].join(' · '));
            summary.title = summary.textContent; toggle.append(summary);
        }
        bar.append(toggle);
        if (!collapsed) {
            for (const field of this.state.spec.features) {
                const control = button(field.label, field.label, () => this.edit(state => state.toggle(field.key)));
                control.title = field.tooltip; control.dataset.field = `features.${field.key}`;
                control.setAttribute('aria-pressed', String(this.state.enabled(field.key))); bar.append(control);
            }
            const seed = button('Local seed', 'Local seed', () => this.edit(state => state.setLocalSeed(!local, this.controller.connected())));
            seed.dataset.field = 'seed.source'; seed.setAttribute('aria-pressed', String(local)); seed.disabled = local && !this.controller.connected();
            seed.title = seed.disabled ? 'Connect seed_input to use an external seed.' : local ? 'Local seed is active; seed_input is ignored.' : 'seed_input is active; enable to use the local seed.';
            bar.append(seed);
        }
        bar.append(runActions(this.controller, { beforeRun: () => {
            if (!this.state.sectionOpen('result')) this.edit(state => state.toggleSection('result'));
        } }));
        parent.append(bar);
    }
    section(parent, key, title, build) {
        const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', title); section.dataset.section = key;
        if (key !== 'seed') section.dataset.textSection = key;
        const header = element('div', 'en-panel-section-header'), open = this.state.sectionOpen(key);
        const toggle = button('', title, () => this.edit(state => state.toggleSection(key)));
        toggle.className = 'en-panel-section-toggle'; toggle.dataset.field = `section.${key}`; toggle.setAttribute('aria-expanded', String(open));
        const summary = element('span', 'en-panel-summary', this.summary(key)); summary.title = summary.textContent; summary.dataset.sectionSummary = key;
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} ${title}`), summary);
        const pin = button('⌖', `Pin ${title}`, () => this.edit(state => state.togglePin(key)));
        pin.dataset.field = `pin.${key}`; pin.setAttribute('aria-pressed', String(this.state.editor.pins?.[key] === true));
        header.append(toggle, pin); section.append(header);
        if (open) { const body = element('div', 'en-panel-section-body'); build(body); section.append(body); }
        parent.append(section);
    }
    summary(key) {
        if (key === 'result') return this.state.editor.lastResult === undefined ? 'Run to preview' : 'Last execution';
        if (key === 'seed') {
            const seed = this.state.config.seed;
            return seed.policy === 'random' ? 'Random each run' : `${{ increment: 'Increment · ', decrement: 'Decrement · ' }[seed.policy] ?? ''}${seed.value}`;
        }
        const text = this.state.config.texts[key].replace(/\s+/g, ' ').trim();
        return text.length > 100 ? `${text.slice(0, 100)}…` : text || 'Empty';
    }
    syncSummaries() {
        for (const item of this.controller.root.querySelectorAll('[data-section-summary]')) item.textContent = item.title = this.summary(item.dataset.sectionSummary);
        const result = this.controller.root.querySelector('textarea[aria-label="Result"]');
        if (result && result.value !== this.state.editor.lastResult) result.value = this.state.editor.lastResult ?? '';
    }
    dispose() { this.textSizes.disconnect(); }
}
