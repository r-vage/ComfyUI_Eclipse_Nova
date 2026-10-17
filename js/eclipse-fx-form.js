/** Jade image/text FX sections with native color pickers and a Director mode bar. */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { EFFECTS } from './eclipse-fx-state.js';

export class FxForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); }
    get state() { return this.controller.state; }
    get config() { return this.state.config; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    connected(name) { return this.controller.node.inputs?.some(input => input.name === name && input.link != null); }
    render() {
        this.dispose();
        const { root } = this.controller;
        const focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        const content = element('div', 'en-panel-content');
        this.bar(content);
        if (this.config.kind === 'image') {
            this.section(content, 'image', 'Image', parent => {
                const grid = this.grid(parent); this.number(grid, 'image_scale'); this.number(grid, 'opacity');
                if (this.connected('mask')) {
                    const label = element('label', 'en-panel-inline'), input = element('input'); input.type = 'checkbox';
                    input.checked = this.config.parameters.invert_mask; input.dataset.field = 'parameters.invert_mask';
                    input.title = 'Invert the connected mask. Without a mask, the source image alpha is used unchanged.';
                    input.onchange = () => this.edit(state => { state.config.parameters.invert_mask = input.checked; }, false);
                    label.append(input, element('span', '', 'Invert mask')); parent.append(label);
                }
                parent.append(element('div', 'en-panel-note', '100% fits the source inside the background. The first source image is used for every background frame.'));
            });
        } else {
            this.section(content, 'text', 'Text & font', parent => this.text(parent));
            this.section(content, 'layout', 'Layout', parent => {
                this.choice(parent, 'Alignment', 'text_align');
                const grid = this.grid(parent); this.number(grid, 'char_per_line'); this.number(grid, 'leading');
            });
        }
        this.section(content, 'placement', 'Placement', parent => {
            const automatic = this.config.kind === 'text' && !this.connected('background_image');
            if (automatic) parent.append(element('div', 'en-panel-note', 'The canvas fits the text and effects. Connect a background to use anchor positioning.'));
            else this.choice(parent, 'Anchor', 'position');
            const grid = this.grid(parent);
            this.number(grid, 'margin_x', 'parameters', automatic ? 'Padding X' : undefined);
            this.number(grid, 'margin_y', 'parameters', automatic ? 'Padding Y' : undefined);
        });
        for (const key of this.state.effects()) if (this.config[key] !== null) {
            this.section(content, key, EFFECTS[key], parent => {
                const grid = this.grid(parent);
                for (const name of this.state.spec.groups[key]) {
                    if (this.state.spec.colors[name]) this.color(grid, name, key);
                    else this.number(grid, name, key);
                }
            });
        }
        root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    bar(parent) {
        const collapsed = this.state.editor.barCollapsed === true, bar = element('div', 'en-panel-bar');
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Mode');
        const toggle = button('', 'Mode', () => this.edit(state => { state.editor.barCollapsed = !collapsed; }));
        toggle.className = 'en-panel-disclosure'; toggle.dataset.field = 'bar'; toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Mode:'));
        if (collapsed) {
            const summary = element('span', 'en-panel-summary', this.state.effects().filter(key => this.config[key] !== null).map(key => EFFECTS[key]).join(' · ') || 'No effects');
            summary.title = summary.textContent; toggle.append(summary);
        }
        bar.append(toggle);
        if (!collapsed) for (const key of this.state.effects()) {
            const control = button(EFFECTS[key], EFFECTS[key], () => this.edit(state => state.toggleEffect(key)));
            control.title = `Enable or disable ${EFFECTS[key].toLowerCase()}. Disabled settings are retained.`;
            control.dataset.field = `effect.${key}`; control.setAttribute('aria-pressed', String(this.config[key] !== null)); bar.append(control);
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
    number(parent, key, group = 'parameters', title) {
        const field = this.state.spec.numbers[key], label = element('label', 'en-panel-field'), input = element('input');
        input.type = 'number'; input.required = true; input.value = this.config[group][key] ?? ''; input.dataset.field = `${group}.${key}`;
        for (const name of ['min', 'max', 'step']) input[name] = field[name];
        input.oninput = () => this.edit(state => { state.config[group][key] = input.value === '' ? null : Number(input.value); }, false);
        label.append(element('span', '', title ?? field.label), input); parent.append(label);
    }
    color(parent, key, group = 'parameters') {
        const [title] = this.state.spec.colors[key], label = element('label', 'en-panel-field'), input = element('input');
        input.type = 'color'; input.dataset.field = `${group}.${key}`; input.title = `Choose ${title.toLowerCase()}`;
        const raw = String(this.config[group][key]).replace(/^#/, '');
        input.value = `#${/^[0-9a-f]{3}$/i.test(raw) ? [...raw].map(c => c + c).join('') : raw}`;
        input.oninput = input.onchange = () => {
            if (this.config[group][key] !== input.value) this.edit(state => { state.config[group][key] = input.value; }, false);
        };
        label.append(element('span', '', title), input); parent.append(label);
    }
    choice(parent, title, key) {
        const choices = this.state.spec.choices[key], current = this.config.parameters[key];
        const control = this.menu.field(parent, title, choices[current] ?? current, Object.values(choices), label => {
            this.edit(state => { state.config.parameters[key] = Object.keys(choices).find(key => choices[key] === label); });
        }); control.dataset.field = `parameters.${key}`;
    }
    text(parent) {
        const label = element('label', 'en-panel-field'), input = element('textarea');
        input.rows = 3; input.maxLength = this.state.spec.maxText; input.value = this.config.parameters.text; input.dataset.field = 'parameters.text';
        input.oninput = () => this.edit(state => { state.config.parameters.text = input.value; }, false);
        label.append(element('span', '', 'Text'), input); parent.append(label);
        if (this.connected('text_input')) parent.append(element('div', 'en-panel-note', 'Connected text_input takes priority when non-None. The panel text is retained.'));
        const font = this.menu.field(parent, 'Font', this.config.parameters.font_file, this.state.spec.fonts,
            value => this.edit(state => { state.config.parameters.font_file = value; })); font.dataset.field = 'parameters.font_file';
        const grid = this.grid(parent);
        this.number(grid, 'font_size'); this.number(grid, 'text_scale');
        this.color(grid, 'text_color'); this.number(grid, 'opacity');
    }
    summary(key) {
        const p = this.config.parameters;
        if (key === 'image') return `${p.image_scale}% · opacity ${p.opacity}%`;
        if (key === 'text') return `${p.font_file} · ${p.font_size} px`;
        if (key === 'layout') return `${this.state.spec.choices.text_align[p.text_align]} · ${p.char_per_line} chars`;
        if (key === 'placement') return `${this.config.kind === 'text' && !this.connected('background_image') ? 'Automatic' : this.state.spec.choices.position[p.position]} · ${p.margin_x} / ${p.margin_y}`;
        if (key === 'stroke') return `${this.config.stroke.stroke_width} px`;
        if (key === 'glow') return `${this.config.glow.glow_intensity} steps · ${this.config.glow.glow_range} px`;
        if (key === 'shadow') return `${this.config.shadow.shadow_offset_x} / ${this.config.shadow.shadow_offset_y} · ${this.config.shadow.shadow_opacity}%`;
        return '';
    }
    syncSummaries() {
        for (const item of this.controller.root.querySelectorAll('[data-section-summary]')) item.textContent = item.title = this.summary(item.dataset.sectionSummary);
    }
    dispose() { this.menu.close(); }
}
