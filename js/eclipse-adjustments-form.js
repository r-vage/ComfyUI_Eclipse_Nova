/** Compact sections ordered from softening through grain, using the shared theme. */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { TITLES } from './eclipse-adjustments-state.js';

export class AdjustmentsForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); }
    get state() { return this.controller.state; }
    get config() { return this.state.config; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    connected(name) { return this.controller.node.inputs?.some(input => input.name === name && input.link != null); }
    supersampleAvailable() { return this.config.scale !== null && (this.connected('upscale_by') || this.config.scale.target !== 'native'); }
    render() {
        this.dispose();
        const { root } = this.controller;
        const focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        const content = element('div', 'en-panel-content'); this.bar(content);
        for (const [key, title] of Object.entries(TITLES)) if (this.config[key] !== null) this.section(content, key, title);
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
        const flags = [
            ['soften', 'Soften', this.config.soften !== null], ['scale', 'Scale', this.config.scale !== null],
            ['supersample', 'Supersample', Boolean(this.config.scale?.supersample) && this.supersampleAvailable()],
            ['color_match', 'Color match', this.config.color_match !== null], ['sharpen', 'Smart sharpen', this.config.sharpen !== null],
            ['detail_enhance', 'Detail filter', this.config.processing.detail_enhance],
            ['per_frame', 'Per frame', this.config.processing.per_frame],
            ['cpu_threads', 'CPU threads', this.config.processing.cpu_threads && !this.config.processing.per_frame],
        ];
        if (collapsed) {
            const summary = element('span', 'en-panel-summary', flags.filter(flag => flag[2]).map(flag => flag[1]).join(' · ') || 'Adjustments');
            summary.title = summary.textContent; toggle.append(summary);
        }
        bar.append(toggle);
        if (!collapsed) for (const [key, title, active] of flags) {
            const control = button(title, title, () => this.edit(state => {
                if (state.spec.optional.includes(key)) state.toggleEffect(key);
                else if (key === 'supersample') state.config.scale.supersample = !state.config.scale.supersample;
                else state.config.processing[key] = !state.config.processing[key];
            }));
            control.dataset.field = `mode.${key}`; control.setAttribute('aria-pressed', String(active));
            control.disabled = key === 'supersample' && !this.supersampleAvailable() || key === 'cpu_threads' && this.config.processing.per_frame;
            control.title = key === 'per_frame' ? 'Finish each frame before starting the next to limit memory use.'
                : key === 'cpu_threads' ? 'Parallelize eligible CPU work across up to four frames when Per frame is off. Model/GPU stages remain serial.'
                    : key === 'supersample' ? 'Resample above the target size before the final resize. Requires Scale with an explicit target; native size or an external factor of 0 skips this.'
                        : key === 'detail_enhance' ? 'Apply the PIL DETAIL filter in Detail & blur.'
                            : `Enable or disable ${title.toLowerCase()}. Disabled settings are retained.`;
            bar.append(control);
        }
        parent.append(bar);
    }
    section(parent, key, title) {
        const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', title);
        const header = element('div', 'en-panel-section-header'), open = this.state.sectionOpen(key);
        const toggle = button('', title, () => this.edit(state => state.toggleSection(key)));
        toggle.className = 'en-panel-section-toggle'; toggle.dataset.field = `section.${key}`; toggle.setAttribute('aria-expanded', String(open));
        const summary = element('span', 'en-panel-summary', this.summary(key)); summary.title = summary.textContent; summary.dataset.sectionSummary = key;
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} ${title}`), summary);
        const pin = button('⌖', `Pin ${title}`, () => this.edit(state => state.togglePin(key)));
        pin.dataset.field = `pin.${key}`; pin.setAttribute('aria-pressed', String(this.state.editor.pins?.[key] === true));
        header.append(toggle, pin); section.append(header);
        if (open) { const body = element('div', 'en-panel-section-body'); this.body(body, key); section.append(body); }
        parent.append(section);
    }
    grid(parent) { const grid = element('div', 'en-panel-grid'); parent.append(grid); return grid; }
    numbers(parent, group, names, disabled = false) { const grid = this.grid(parent); for (const key of names) this.field(grid, group, key, disabled); }
    note(parent, text) { parent.append(element('div', 'en-panel-note', text)); }
    body(parent, key) {
        const values = this.config[key];
        if (key === 'soften') {
            this.field(parent, key, 'method'); const names = ['strength'];
            if (['gaussian', 'bilateral', 'median', 'edge_blur'].includes(values.method)) names.push('radius');
            if (values.method === 'anisotropic') names.push('iterations');
            this.numbers(parent, key, names); this.note(parent, 'Positive strength softens; negative strength sharpens.');
        } else if (key === 'scale') {
            this.field(parent, key, 'model'); const external = this.connected('upscale_by');
            this.field(parent, key, 'target', external);
            if (values.target === 'factor') this.numbers(parent, key, ['factor'], external);
            if (values.target === 'fixed') this.numbers(parent, key, ['width', 'height'], external);
            if (external) this.note(parent, 'Connected upscale_by overrides this target when non-None. 0 keeps native model size, or the original size without a model. Local settings are retained.');
            const grid = this.grid(parent); this.field(grid, key, 'resampling');
            if (values.target !== 'native' || external) this.field(grid, key, 'divisor');
            if (values.supersample && this.supersampleAvailable()) this.field(parent, key, 'supersample_factor');
            this.note(parent, 'Factors use the original image size. Final dimensions round to the nearest divisor; ties round up. Native size skips rounding and supersampling.');
        } else if (key === 'color_match') {
            this.field(parent, key, 'method'); this.numbers(parent, key, ['strength']); this.field(parent, key, 'pairing');
            if (!this.connected('image_ref')) this.note(parent, 'Connect image_ref to transfer colors. Strength 0 skips this stage.');
        } else if (key === 'grade') {
            this.field(parent, key, 'lut'); this.numbers(parent, key, ['strength', 'solarize']);
            this.note(parent, 'Solarize is applied before the LUT. 0 disables solarize.');
        } else if (key === 'finish') {
            this.numbers(parent, key, ['vignette', 'aberration']);
            this.numbers(parent, key, ['center_x', 'center_y']);
            const grid = element('div', 'en-panel-grid en-panel-numbers'); parent.append(grid);
            for (const name of ['grain', 'grain_size', 'grain_color']) this.field(grid, key, name);
            this.note(parent, 'Grain is added last and changes on each run when enabled. Alpha is preserved.');
        } else {
            this.numbers(parent, key, Object.keys(this.state.spec.groups[key]));
            if (key === 'color') this.note(parent, 'Brightness → multiplicative contrast → saturation → temperature/tint → hue.');
            if (key === 'detail') this.note(parent, 'Sharpness 1 is neutral. The Detail filter switch is in Mode.');
        }
    }
    field(parent, group, key, disabled = false) {
        const field = this.state.spec.groups[group][key], value = this.config[group][key], path = `${group}.${key}`;
        if (field.choices || field.files) {
            const choices = field.choices ?? { '': 'None', ...Object.fromEntries(this.state.spec.files[field.files].map(name => [name, name])) };
            const control = this.menu.field(parent, field.label, choices[value] ?? value, Object.values(choices), label => {
                this.edit(state => { state.config[group][key] = Object.keys(choices).find(name => choices[name] === label); });
            });
            control.dataset.field = path; control.disabled = disabled; return;
        }
        const label = element('label', 'en-panel-field'), input = element('input');
        input.type = 'number'; input.required = true; input.value = value ?? ''; input.dataset.field = path; input.disabled = disabled;
        for (const name of ['min', 'max', 'step']) input[name] = field[name];
        input.oninput = () => this.edit(state => { state.config[group][key] = input.value === '' ? null : Number(input.value); }, false);
        label.append(element('span', '', field.label), input); parent.append(label);
    }
    summary(key) {
        const value = this.config[key]; if (!value) return '';
        if (key === 'soften') return `${value.method} · ${value.strength}`;
        if (key === 'scale') return this.connected('upscale_by') ? 'upscale_by input' : value.target === 'native' ? 'Native size' : value.target === 'factor' ? `${value.factor}× · ${value.resampling}` : `${value.width} × ${value.height}`;
        if (key === 'color_match') return `${value.method} · ${value.strength}`;
        if (key === 'sharpen') return `${value.amount} · blend ${value.blend}`;
        if (key === 'grade') return [value.lut && value.strength > 0 ? value.lut : '', value.solarize ? `Solarize ${value.solarize}` : ''].filter(Boolean).join(' · ') || 'Off';
        if (key === 'finish') return [value.vignette ? `Vignette ${value.vignette}` : '', value.aberration ? `CA ${value.aberration}` : '', value.grain ? `Grain ${value.grain}` : ''].filter(Boolean).join(' · ') || 'Off';
        const changed = Object.entries(value).filter(([name, current]) => current !== this.state.spec.groups[key][name].default).length;
        return key === 'detail' && this.config.processing.detail_enhance ? `${changed + 1} active` : changed ? `${changed} adjusted` : 'Neutral';
    }
    syncSummaries() {
        for (const item of this.controller.root.querySelectorAll('[data-section-summary]')) item.textContent = item.title = this.summary(item.dataset.sectionSummary);
    }
    dispose() { this.menu.close(); }
}
