/** SPDX-License-Identifier: Apache-2.0
 * Shared compact reference and sheet panels on the Nova theme surface.
 */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { TextFieldSizes } from './eclipse-panel-text-layout.js';

export class CharacterForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); this.textSizes = new TextFieldSizes(controller); }
    get state() { return this.controller.state; }
    get params() { return this.state.config.parameters; }
    get kind() { return this.state.config.kind; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    connected(key) { return this.controller.node.inputs?.some(input => input.name === key && input.link != null); }
    render() {
        this.dispose();
        const { root } = this.controller;
        const focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        const content = element('div', 'en-panel-content');
        if (this.kind === 'prepare') {
            this.bar(content, 'role', 'Role'); this.bar(content, 'mode', 'Mode');
            const mode = this.params.mode;
            this.note(content, { reference: 'Select passes the original image. Preparation generation is skipped.',
                extract: 'Uses the source for extraction. Connect the preparation sampler to Select.',
                generate: 'Generates from text. The source image branch is skipped.', disabled: 'Select returns no image. Source and preparation generation are skipped.' }[mode]);
            if (['extract', 'generate'].includes(mode)) {
                this.promptNote(content);
                if (!this.connected('positive_override')) this.textSections(content);
            }
        } else if (this.kind === 'reference_pack') {
            this.canvas(content); this.textSections(content); this.report(content);
        } else if (this.kind === 'sheet_pack') {
            this.bar(content, 'stage', 'Stage');
            if (this.params.stage === 'mannequin') this.bar(content, 'generation_mode', 'Mode');
            const toggles = this.params.stage === 'mannequin' && this.params.generation_mode === 'Reference' ? ['use_front_body', 'use_rear_body']
                : this.params.stage === 'sheet' ? ['use_wardrobe'] : this.params.stage === 'dataset' ? ['use_rear'] : [];
            if (toggles.length) this.bar(content, 'include', 'Include', toggles);
            this.canvas(content);
            if (this.params.stage === 'mannequin') this.section(content, 'mannequin', 'Mannequin', parent => {
                const grid = this.grid(parent); this.choice(grid, 'gender');
                if (this.params.generation_mode === 'Preset') for (const key of ['build', 'muscularity', 'breast_size', 'chest_breadth', 'hip_width', 'buttock_size']) this.choice(grid, key);
                this.note(parent, this.params.generation_mode === 'Preset'
                    ? 'Uses a blank size-setting canvas and skips all image inputs. Attributes are independent of gender.'
                    : 'Uses optional layout and enabled physique references. Body presets are retained but ignored; Gender still applies.');
            });
            this.textSections(content); this.promptNote(content); this.report(content);
        } else {
            this.bar(content, 'mode', 'Mode');
            this.section(content, 'crop', 'Crop', parent => {
                if (this.params.mode === 'manual') { const grid = this.grid(parent); this.number(grid, 'front_end'); this.number(grid, 'rear_end'); }
                this.number(parent, 'gutter');
                this.note(parent, this.params.mode === 'auto' ? 'Splits the actual image width into thirds. Manual boundaries are retained and ignored.' : 'Boundaries are fractions of the full image width. Preview the crops before using them.');
                this.note(parent, 'Gutter trims both edges of each panel. Outputs stay three separate single images.');
            });
            this.report(content);
        }
        root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    bar(parent, key, title, toggles = null) {
        const collapsed = this.state.editor.bars?.[key] === true, bar = element('div', 'en-panel-bar');
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', title);
        const toggle = button('', title, () => this.edit(state => { (state.editor.bars ??= {})[key] = !collapsed; }));
        toggle.className = 'en-panel-disclosure'; toggle.dataset.field = `bar.${key}`; toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', `${title}:`));
        const labels = this.state.spec.toggles;
        if (collapsed) toggle.append(element('span', 'en-panel-summary', toggles
            ? toggles.filter(name => this.params[name]).map(name => labels[name]).join(' · ') || 'None'
            : this.state.spec.choices[key][this.params[key]] ?? this.params[key]));
        bar.append(toggle);
        if (!collapsed) {
            for (const [value, label] of toggles ? toggles.map(name => [name, labels[name]]) : Object.entries(this.state.spec.choices[key])) {
                const control = button(label, label, () => this.edit(state => {
                    if (toggles) state.config.parameters[value] = !state.config.parameters[value];
                    else state.config.parameters[key] = value;
                }));
                control.dataset.field = `parameters.${toggles ? value : key}.${value}`;
                control.setAttribute('aria-pressed', String(toggles ? this.params[value] : this.params[key] === value));
                control.title = this.kind === 'sheet_split' ? 'Auto splits actual thirds; Manual uses saved boundaries.' : this.state.spec.tips[toggles ? value : key] ?? label;
                bar.append(control);
            }
        }
        parent.append(bar);
    }
    section(parent, key, title, build) {
        const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', title);
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
    canvas(parent) {
        this.section(parent, 'canvas', 'Canvas', body => {
            const grid = this.grid(body); this.number(grid, 'width'); this.number(grid, 'height');
            const connected = ['width', 'height'].filter(key => this.connected(key));
            if (connected.length) this.note(body, `Connected ${connected.join(' and ')} take priority when non-None. Local dimensions are retained.`);
            this.note(body, 'Multiples of 32, from 256 to 2048. Set the Qwen encoder resolution to 0.');
        });
    }
    textSections(parent) {
        for (const [key, [title]] of Object.entries(this.state.spec.texts)) this.section(parent, key, title, body => {
            this.textarea(body, key, title, this.params[key], false);
            if (this.connected(key)) this.note(body, 'Connected text takes priority when non-None. Empty connected text clears it. Local text is retained.');
        });
    }
    promptNote(parent) {
        const positive = this.connected('positive_override'), negative = this.connected('negative_override');
        this.note(parent, `Positive: ${positive ? 'connected override' : 'file default'} · Negative: ${negative ? 'connected override' : 'file default'}.`
            + (positive ? this.kind === 'prepare' ? ' Positive override replaces Description and Instructions too.' : ' Details and reference roles still apply.' : ''));
    }
    report(parent) {
        this.section(parent, 'report', 'Report', body => {
            this.textarea(body, 'report', 'Last report', this.state.editor.lastReport ?? '', true);
            this.note(body, 'Last execution only. Queue after changing settings to update the role map or crop boundaries.');
        });
    }
    grid(parent) { const grid = element('div', 'en-panel-grid'); parent.append(grid); return grid; }
    note(parent, text) { parent.append(element('div', 'en-panel-note', text)); }
    number(parent, key) {
        const field = this.state.spec.numbers[key], label = element('label', 'en-panel-field'), input = element('input');
        input.type = 'number'; input.required = true; input.value = this.params[key] ?? ''; input.dataset.field = `parameters.${key}`;
        for (const name of ['min', 'max', 'step']) input[name] = field[name]; input.title = this.state.spec.tips[key];
        input.oninput = () => this.edit(state => { state.config.parameters[key] = input.value === '' ? null : Number(input.value); }, false);
        label.append(element('span', '', field.label), input); parent.append(label);
    }
    textarea(parent, key, title, value, readOnly) {
        const label = element('label', 'en-panel-field'), input = element('textarea');
        input.rows = readOnly ? 5 : 3; input.maxLength = this.state.spec.maxText; input.value = value; input.readOnly = readOnly;
        input.title = this.state.spec.tips[key] ?? title; this.textSizes.attach(input, key);
        if (!readOnly) input.oninput = () => this.edit(state => { state.config.parameters[key] = input.value; }, false);
        label.append(element('span', '', title), input); parent.append(label);
    }
    choice(parent, key) {
        const title = key.replaceAll('_', ' ').replace(/^./, char => char.toUpperCase()), choices = this.state.spec.choices[key];
        const control = this.menu.field(parent, title, this.params[key], Object.keys(choices), value => this.edit(state => { state.config.parameters[key] = value; }));
        control.dataset.field = `parameters.${key}`;
        control.title = 'Choices come from prompts/character_sheets.json. Unspecified adds no instruction. Edit descriptions there; restart and refresh to load new names.';
    }
    summary(key) {
        if (key === 'canvas') return ['width', 'height'].map(name => this.connected(name) ? `${name} input` : this.params[name]).join(' × ');
        if (key === 'mannequin') return [this.params.gender, ...(this.params.generation_mode === 'Preset' ? [this.params.build] : ['Reference'])].join(' · ');
        if (key === 'crop') return `${this.params.mode === 'auto' ? 'Thirds' : `${this.params.front_end} / ${this.params.rear_end}`} · Gutter ${this.params.gutter}`;
        if (key === 'report') return this.state.editor.lastReport ? 'Last execution' : 'Not run';
        if (this.connected(key)) return 'Connected input';
        return this.params[key]?.trim() ? 'Local text' : 'Empty';
    }
    syncSummaries() {
        for (const item of this.controller.root.querySelectorAll('[data-section-summary]')) item.textContent = item.title = this.summary(item.dataset.sectionSummary);
    }
    dispose() { this.menu.close(); this.textSizes.disconnect(); }
}
