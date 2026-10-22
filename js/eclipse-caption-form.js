/** Compact caption sections and color pickers on the shared Nova surface.
 * Copyright (c) 2026 r-vage. MIT License.
 */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { seedControls } from './eclipse-panel-seed-controls.js';

export class CaptionForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); }
    get state() { return this.controller.state; }
    get params() { return this.state.config.parameters; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    connected(key) { return this.controller.node.inputs?.some(input => input.name === key && input.link != null); }
    render() {
        this.dispose();
        const { root } = this.controller;
        const focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        const content = element('div', 'en-panel-content');
        this.bar(content);
        this.section(content, 'canvas', 'Canvas', parent => {
            const grid = this.grid(parent);
            for (const key of ['width', 'height', 'fps']) this.number(grid, key);
            this.color(grid, 'background_color');
            if (this.state.spec.pipe_only) this.note(parent, 'IO Lyric Captions can override dimensions, FPS, trim and seed. Appearance and alignment choices stay local to this renderer. The output pipe carries the settings, lyrics and timing actually used.');
            const connected = ['width', 'height', 'fps'].filter(key => this.connected(key));
            if (connected.length) this.note(parent, `Connected ${connected.join(', ')} override local values when non-None. Local settings are retained.`);
            if (this.connected('background')) this.note(parent, 'The background starts at clip zero and holds its last frame if shorter. Exact frame timelines require matching FPS. Background audio is ignored.');
        });
        this.section(content, 'text', 'Text & font', parent => {
            const font = this.menu.field(parent, 'Font', this.params.font_file, this.state.spec.fonts,
                value => this.edit(state => { state.config.parameters.font_file = value; }));
            font.dataset.field = 'parameters.font_file';
            const grid = this.grid(parent);
            this.number(grid, 'font_size'); this.number(grid, 'caption_transparency'); this.color(grid, 'text_color');
            if (this.params.mode === 'active-word') this.color(grid, 'highlight_color');
            this.number(grid, 'outline_width'); this.color(grid, 'outline_color');
        });
        this.section(content, 'placement', 'Placement', parent => {
            if (!this.state.floating) this.choice(parent, 'position', 'Position');
            const grid = this.grid(parent); this.number(grid, 'margin_x'); this.number(grid, 'margin_y');
            if (this.state.floating) this.note(parent, 'Floating captions are placed inside the centered circle. Margins reserve space around the canvas.');
        });
        if (this.state.animated) this.section(content, 'animation', 'Animation', parent => {
            if (!this.state.floating) this.choice(parent, 'rotation_axis', 'Rotation axis');
            const grid = this.grid(parent);
            for (const key of ['fade_in', 'fade_out', 'min_display']) this.number(grid, key);
            if (this.params.mode.endsWith('-words')) this.number(grid, 'max_words');
            if (this.state.floating) for (const key of ['circle_radius', 'float_distance', 'max_simultaneous']) this.number(grid, key);
        });
        if (this.params.enable_glow) this.section(content, 'glow', 'Glow', parent => {
            const grid = this.grid(parent);
            for (const key of ['glow_intensity', 'glow_range', 'glow_blur']) this.number(grid, key);
            for (const key of ['glow_inner_color', 'glow_outer_color']) this.color(grid, key);
        });
        this.section(content, 'alignment', 'Alignment & timing', parent => {
            const grid = this.grid(parent);
            this.choice(grid, 'language', 'Language'); this.choice(grid, 'device', 'Device');
            if (this.state.spec.choices.word_timing) this.choice(grid, 'word_timing', 'Word timing');
            this.choice(grid, 'unmatched_passages', 'Unmatched passages'); this.number(grid, 'timing_adjustment');
            if (this.state.spec.pipe_only) {
                for (const key of ['trim_start', 'duration']) this.number(grid, key);
                this.note(parent, 'Blank correction fields keep the original lyrics and timing. Wording edits reuse reference phrases; full corrected timing takes priority. Without a reference, the shared transcription helper creates one.');
            } else this.note(parent, this.connected('corrected_timing')
                ? 'Non-empty corrected timing bypasses alignment and isolated vocals. It must describe the full song before trimming.'
                : 'Aligns the full song; optional vocals must start at zero and match its duration. Changing appearance reuses cached alignment.');
            this.note(parent, 'trim_start and duration trim audio and captions together. Duration 0 renders the remainder. Positive timing adjustment delays captions.');
        });
        this.section(content, 'seed', 'Seed', parent => {
            seedControls(parent, this.controller);
            if (this.state.spec.pipe_only) this.note(parent, 'A seed supplied in the pipe takes priority over this local seed.');
            this.note(parent, 'Repeatable floating-caption positions across the full song and trimmed clips. Other caption modes do not use the seed.');
        });
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
        if (collapsed) toggle.append(element('span', 'en-panel-summary', `${this.state.spec.choices.mode[this.params.mode]}${this.params.enable_glow ? ' · Glow' : ''}`));
        bar.append(toggle);
        if (!collapsed) {
            for (const [value, label] of Object.entries(this.state.spec.choices.mode)) {
                const control = button(label, label, () => this.edit(state => { state.config.parameters.mode = value; }));
                control.dataset.field = `mode.${value}`; control.setAttribute('aria-pressed', String(this.params.mode === value)); bar.append(control);
            }
            const glow = button('Glow', 'Glow', () => this.edit(state => { state.config.parameters.enable_glow = !state.config.parameters.enable_glow; }));
            glow.title = 'Enable or disable glow. Disabled settings are retained.';
            glow.dataset.field = 'parameters.enable_glow'; glow.setAttribute('aria-pressed', String(this.params.enable_glow)); bar.append(glow);
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
    grid(parent) { const grid = element('div', 'en-panel-grid'); parent.append(grid); return grid; }
    note(parent, text) { parent.append(element('div', 'en-panel-note', text)); }
    number(parent, key) {
        const field = this.state.spec.numbers[key], label = element('label', 'en-panel-field'), input = element('input');
        input.type = 'number'; input.required = true; input.value = this.params[key] ?? ''; input.dataset.field = `parameters.${key}`;
        for (const name of ['min', 'max', 'step']) input[name] = field[name];
        input.title = this.state.spec.tips[key] ?? field.label;
        input.oninput = () => this.edit(state => { state.config.parameters[key] = input.value === '' ? null : Number(input.value); }, false);
        label.append(element('span', '', field.label), input); parent.append(label);
    }
    color(parent, key) {
        const [title] = this.state.spec.colors[key], label = element('label', 'en-panel-field'), input = element('input');
        input.type = 'color'; input.value = this.params[key]; input.dataset.field = `parameters.${key}`; input.title = `Choose ${title.toLowerCase()}`;
        input.oninput = input.onchange = () => {
            if (this.params[key] !== input.value) this.edit(state => { state.config.parameters[key] = input.value; }, false);
        };
        label.append(element('span', '', title), input); parent.append(label);
    }
    choice(parent, key, title) {
        const choices = this.state.spec.choices[key], current = this.params[key];
        const control = this.menu.field(parent, title, choices[current] ?? current, Object.values(choices), label => {
            this.edit(state => { state.config.parameters[key] = Object.keys(choices).find(key => choices[key] === label); });
        }); control.dataset.field = `parameters.${key}`;
        if (this.state.spec.tips[key]) control.title = this.state.spec.tips[key];
    }
    summary(key) {
        const p = this.params;
        if (key === 'canvas') return `${p.width} × ${p.height} · ${p.fps} FPS${['width', 'height', 'fps'].some(k => this.connected(k)) ? ' · Input overrides' : ''}`;
        if (key === 'text') return `${p.font_file} · ${p.font_size} px`;
        if (key === 'placement') return `${this.state.floating ? 'Floating' : this.state.spec.choices.position[p.position]} · ${p.margin_x} / ${p.margin_y}`;
        if (key === 'animation') return `${p.fade_in} / ${p.fade_out} s · ${p.min_display} s hold`;
        if (key === 'glow') return `${p.glow_intensity} steps · ${p.glow_range} px`;
        if (key === 'alignment') return `${p.language} · ${this.state.spec.choices.word_timing?.[p.word_timing] ?? 'Whisper'} · ${this.state.spec.choices.unmatched_passages[p.unmatched_passages]} · ${p.timing_adjustment} s`;
        const seed = this.state.config.seed;
        return seed.policy === 'fixed' ? seed.value : { random: 'Random each run', increment: 'Increment each run', decrement: 'Decrement each run' }[seed.policy];
    }
    syncSummaries() {
        for (const item of this.controller.root.querySelectorAll('[data-section-summary]')) item.textContent = item.title = this.summary(item.dataset.sectionSummary);
    }
    dispose() { this.menu.close(); }
}
