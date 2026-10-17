/** Compact Prompt, Result and Seed sections for the wildcard text/list node. */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { seedControls } from './eclipse-panel-seed-controls.js';
import { TextFieldSizes } from './eclipse-panel-text-layout.js';
import { runActions } from './eclipse-panel-run.js';

export class WildcardForm {
    constructor(controller) {
        this.controller = controller; this.menu = new SearchMenu();
        this.textSizes = new TextFieldSizes(controller, { bounded: true });
    }
    get state() { return this.controller.state; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    render() {
        this.textSizes.disconnect(); this.menu.close(); const { root } = this.controller;
        const content = element('div', 'en-panel-content en-panel-text-layout'); this.bar(content);
        if (this.state.config.mode === 'populate') this.section(content, 'prompt', 'Prompt', parent => this.prompt(parent));
        this.section(content, 'result', 'Result', parent => {
            const fixed = this.state.config.mode === 'fixed';
            const actions = element('div', 'en-panel-inline');
            const wrap = button('Wrap', 'Wrap long lines', () => this.edit(state => { state.editor.wrap = state.editor.wrap === false; }));
            wrap.setAttribute('aria-pressed', String(this.state.editor.wrap !== false)); actions.append(wrap);
            if (!fixed) {
                const preview = button('↻', 'Update preview', () => this.controller.preview(true));
                preview.disabled = this.controller.hasConnectedValues(); actions.append(preview);
            }
            parent.append(actions);
            const input = this.textarea('Result', this.state.result()); input.readOnly = !fixed;
            if (fixed) input.oninput = () => this.edit(state => { state.config.texts.result = input.value; }, false);
            parent.append(input);
            const note = element('div', 'en-panel-note', this.controller.resultStatus()); note.setAttribute('role', 'status');
            parent.append(note);
        });
        if (this.state.config.mode === 'populate' && this.state.config.seed.source === 'local') {
            this.section(content, 'seed', 'Seed', body => seedControls(body, this.controller));
        }
        this.textSizes.layout(content);
        root.replaceChildren(content); this.controller.measure();
    }
    textarea(name, value) {
        const input = element('textarea'); input.rows = 4; input.maxLength = this.state.spec.maxText;
        input.setAttribute('aria-label', name); input.dataset.field = name.toLowerCase(); input.value = value;
        input.wrap = this.state.editor.wrap === false ? 'off' : 'soft';
        input.style.whiteSpace = input.wrap === 'off' ? 'pre' : 'pre-wrap';
        this.textSizes.attach(input, input.dataset.field);
        return input;
    }
    prompt(parent) {
        const connected = this.controller.connected('wildcard_text');
        const input = this.textarea('Prompt', this.state.config.texts.prompt);
        input.placeholder = 'Use __wildcards__ or {option1|option2}. One prompt per line.';
        input.disabled = connected;
        input.oninput = () => this.edit(state => { state.config.texts.prompt = input.value; }, false);
        const actions = element('div', 'en-panel-inline');
        const select = button('Insert wildcard…', 'Insert wildcard', () => this.controller.openWildcards(select, input));
        select.setAttribute('role', 'combobox'); select.setAttribute('aria-expanded', 'false'); select.setAttribute('aria-haspopup', 'listbox');
        select.disabled = connected;
        const refresh = button('↻', 'Reload wildcard files', () => this.controller.reloadWildcards(refresh));
        actions.append(select, refresh); parent.append(actions, input);
        if (connected) parent.append(element('div', 'en-panel-note', 'Prompt comes from wildcard_text.'));
        if (this.controller.connected('substitutions')) parent.append(element('div', 'en-panel-note', 'Connected substitutions are applied during execution.'));
    }
    bar(parent) {
        const collapsed = this.state.editor.barCollapsed === true, bar = element('div', 'en-panel-bar en-panel-with-run');
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Mode');
        const toggle = button('', 'Mode', () => this.edit(state => { state.editor.barCollapsed = !collapsed; }));
        toggle.className = 'en-panel-disclosure'; toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Mode:'));
        const local = this.state.config.seed.source === 'local', populate = this.state.config.mode === 'populate';
        if (collapsed) toggle.append(element('span', 'en-panel-summary', populate ? `Populate · ${local ? 'Local seed' : 'Input seed'}` : 'Fixed'));
        bar.append(toggle);
        if (!collapsed) {
            for (const [mode, label] of [['populate', 'Populate'], ['fixed', 'Fixed']]) {
                const control = button(label, label, () => this.edit(state => state.setMode(mode)));
                control.setAttribute('aria-pressed', String(this.state.config.mode === mode));
                control.title = mode === 'populate' ? 'Expand Prompt using the seed each run.' : 'Keep the displayed Result and edit it directly. Prompt, substitutions and seed are ignored.';
                bar.append(control);
            }
            if (populate) {
                const control = button('Local seed', 'Local seed', () => this.edit(state => state.setLocalSeed(!local, this.controller.connected('seed_input'))));
                control.disabled = local && !this.controller.connected('seed_input'); control.setAttribute('aria-pressed', String(local));
                control.title = control.disabled ? 'Connect seed_input to use an external seed.' : local ? 'Local seed is active; seed_input is ignored.' : 'seed_input is active; enable to use the local seed.';
                bar.append(control);
            }
        }
        bar.append(runActions(this.controller, { beforeRun: () => {
            this.controller.cancelPreview();
            if (!this.state.sectionOpen('result')) this.edit(state => state.toggleSection('result'));
        } }));
        parent.append(bar);
    }
    section(parent, key, title, build) {
        const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', title);
        if (key === 'prompt' || key === 'result') section.dataset.textSection = key;
        const header = element('div', 'en-panel-section-header'), open = this.state.sectionOpen(key);
        const toggle = button('', title, () => this.edit(state => state.toggleSection(key)));
        toggle.className = 'en-panel-section-toggle'; toggle.setAttribute('aria-expanded', String(open));
        const summary = element('span', 'en-panel-summary', this.summary(key)); summary.dataset.sectionSummary = key; summary.title = summary.textContent;
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} ${title}`), summary);
        const pin = button('⌖', `Pin ${title}`, () => this.edit(state => state.togglePin(key)));
        pin.setAttribute('aria-pressed', String(this.state.editor.pins?.[key] === true));
        header.append(toggle, pin); section.append(header);
        if (open) { const body = element('div', 'en-panel-section-body'); build(body); section.append(body); }
        parent.append(section);
    }
    summary(key) {
        if (key === 'result') return '';
        if (key === 'seed') {
            const seed = this.state.config.seed;
            return seed.policy === 'random' ? 'Random each run' : `${{ increment: 'Increment · ', decrement: 'Decrement · ' }[seed.policy] ?? ''}${seed.value}`;
        }
        if (key === 'prompt' && this.controller.connected('wildcard_text')) return 'Connected input';
        const text = this.state.config.texts.prompt;
        return text.replace(/\s+/g, ' ').trim().slice(0, 100) || 'Empty';
    }
    syncSummaries() {
        for (const item of this.controller.root.querySelectorAll('[data-section-summary]')) item.textContent = item.title = this.summary(item.dataset.sectionSummary);
        const output = this.controller.root.querySelector('textarea[aria-label="Result"]');
        if (output?.readOnly) output.value = this.state.result();
        const note = this.controller.root.querySelector('[role="status"]'); if (note) note.textContent = this.controller.resultStatus();
    }
    dispose() { this.textSizes.disconnect(); this.menu.close(); this.controller.cancelPreview(); }
}
