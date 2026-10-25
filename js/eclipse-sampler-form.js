/** Shared compact controls for the structured settings, sampler and detailer. */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { FEATURES } from './eclipse-sampler-state.js';
import { seedControls } from './eclipse-panel-seed-controls.js';

export class SamplerForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); }
    get state() { return this.controller.state; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    render() {
        this.menu.close();
        const root = this.controller.root;
        const focused = root.contains(document.activeElement) ? document.activeElement?.dataset.field : null;
        const content = element('div', 'en-panel-content');
        const { config, spec } = this.state, p = config.parameters, settings = spec.profile === 'settings';
        const choices = settings ? FEATURES.map(([key, label]) => [key, label, this.state.enabled(key)]) : spec.profile === 'detailer'
            ? ['allow_overwrite', 'noise_mask', 'force_inpaint', 'inpaint_model', 'tiled_encode', 'tiled_decode', 'live_preview'].map(key => [key, spec.fields[key].label, p[key] === true]) : [
            ['allow_overwrite', 'Use pipe settings', p.allow_overwrite],
            ['tiled_decode', 'Tiled decode', p.tiled_decode], ['alpha', 'Alpha', p.alpha === true],
            ['preview_mode', 'Preview', p.preview_mode === 'Preview'],
        ];
        if (spec.profile === 'advanced') choices.unshift(['two_stage', 'Two-stage', p.two_stage], ['latent_upscale', 'Latent upscale', p.latent_upscale], ...['qwen_schedule', 'dit_guidance', 'detail_daemon'].map(key => [key, spec.fields[key].label, p[key]]));
        const bar = element('div', 'en-panel-bar'), collapsed = this.state.editor.barCollapsed === true;
        bar.dataset.collapsed = String(collapsed);
        const title = settings ? 'Include' : 'Options'; bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', title);
        const summary = choices.filter(([, , enabled]) => enabled).map(([, label]) => label).join(' · ') || 'None';
        const disclosure = button('', title, () => this.edit(state => { state.editor.barCollapsed = !collapsed; }));
        disclosure.dataset.field = 'bar'; disclosure.className = 'en-panel-disclosure'; disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', `${title}:`));
        if (collapsed) { const text = element('span', 'en-panel-summary', summary); text.title = summary; disclosure.append(text); }
        bar.append(disclosure);
        if (!collapsed) for (const [key, label, enabled] of choices) {
            const control = button(label, label, () => this.edit(state => {
                if (settings) state.toggle(key);
                else state.config.parameters[key] = key === 'preview_mode' ? enabled ? 'None' : 'Preview' : !enabled;
            }));
            if (spec.fields[key]?.tooltip) control.title = spec.fields[key].tooltip;
            control.dataset.field = `feature.${key}`; control.setAttribute('aria-pressed', String(enabled));
            if (key === 'allow_overwrite') control.title = settings
                ? 'Allow direct inputs in IO Sampler Settings to override values from this pipe.'
                : 'Use values supplied by the pipe. Missing pipe values use the local settings below.';
            if (spec.profile === 'advanced' && key === 'allow_overwrite') control.title = 'Use supplied pipe values for both stages, seeds, upscale, preview and decode. Missing values keep the local settings.';
            if (key === 'latent_upscale') { control.disabled = !p.two_stage; control.title = 'Resize the latent between stages. Only available in two-stage mode.'; }
            if (key === 'alpha') control.title = 'Keep decoded transparency. Off by default to return RGB instead of RGBA.';
            if (key === 'live_preview') control.title = 'Show or hide live sampling and final images immediately. Turning this off keeps the image output.';
            bar.append(control);
        }
        content.append(bar);
        if (spec.profile === 'advanced') this.advanced(content);
        else if (spec.profile === 'detailer') this.detailer(content);
        else this.sampling(content);
        this.controls = content;
        if (this.controller.preview) {
            content.style.flex = '0 0 auto';
            const layout = element('div', 'en-panel-content');
            layout.append(content, this.controller.preview.element); root.replaceChildren(layout);
            this.controller.preview.sync();
        } else root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    sampling(content, includeSeed = true) {
        const { config, spec } = this.state, p = config.parameters;
        const selectors = element('div', 'en-panel-grid'), numbers = element('div', 'en-panel-grid en-panel-numbers');
        for (const key of ['sampler_name', 'scheduler']) if (this.state.enabled(key)) {
            const field = spec.fields[key];
            const trigger = this.menu.field(selectors, field.label, p[key], field.options,
                value => this.edit(state => { state.config.parameters[key] = value; }));
            trigger.dataset.field = key;
            if (spec.profile === 'advanced' && key === 'scheduler' && p.qwen_schedule) { trigger.disabled = true; trigger.title = 'Qwen schedule supplies sigmas for this stage.'; }
        }
        for (const key of ['steps', 'cfg', 'denoise', 'guidance', 'upscale_value']) {
            if (key === 'denoise' && spec.profile === 'advanced' && p.two_stage) continue;
            if (this.state.enabled(key)) this.number(numbers, key);
        }
        content.append(selectors, numbers);
        if (this.state.enabled('sigmas_denoise')) {
            const group = element('div', 'en-panel-grid'); group.setAttribute('role', 'group'); group.setAttribute('aria-label', 'Noise injection');
            this.number(group, 'sigmas_denoise'); this.number(group, 'noise_strength'); content.append(group);
        }
        if (includeSeed && this.state.enabled('seed')) this.seed(content);
        if (spec.profile === 'sampler') this.number(content, 'tile_size', 'en-panel-inline', !p.tiled_decode);
        if (!Object.keys(p).length && !config.seed) content.append(element('div', 'en-panel-note', 'Select the settings to include in the pipe.'));
    }
    advanced(content) {
        const p = this.state.config.parameters;
        this.section(content, 'sampler', p.two_stage ? 'Stage 1' : 'Sampler', group => {
            this.sampling(group, false);
            if (p.two_stage) this.stageRange(group, false);
        });
        if (p.two_stage && p.latent_upscale) this.section(content, 'upscale', 'Latent upscale', group => {
            const field = this.state.spec.fields.upscale_method;
            this.menu.field(group, field.label, p.upscale_method, field.options,
                value => this.edit(state => { state.config.parameters.upscale_method = value; }));
            this.number(group, 'upscale_factor');
        });
        if (p.two_stage) this.section(content, 'stage2', 'Stage 2', group => {
            group.append(element('div', 'en-panel-note', 'Uses model_2 from the PIPE when supplied; otherwise reuses model_1. Use pipe settings does not affect model selection.'));
            const selectors = element('div', 'en-panel-grid'), numbers = element('div', 'en-panel-grid');
            for (const key of ['second_sampler_name', 'second_scheduler']) {
                const field = this.state.spec.fields[key];
                const control = this.menu.field(selectors, field.label, p[key], field.options,
                    value => this.edit(state => { state.config.parameters[key] = value; }));
                control.dataset.field = key;
                if (key === 'second_scheduler' && p.qwen_schedule) { control.disabled = true; control.title = 'Qwen schedule supplies sigmas for Stage 2 at its actual resolution.'; }
            }
            for (const key of ['second_steps', 'second_cfg']) this.number(numbers, key);
            this.number(numbers, 'second_denoise', 'en-panel-field', p.second_start !== 0);
            group.append(selectors, numbers); this.stageRange(group, true);
        });
        for (const [key, enabled, title, prefix] of [
            ['qwen', p.qwen_schedule, 'Qwen schedule', 'qwen_'],
            ['dit', p.dit_guidance, 'DiT skip guidance', 'dit_'],
            ['detail', p.detail_daemon, 'Detail Daemon', 'detail_'],
        ]) if (enabled) this.section(content, key, title, group => {
            const grid = element('div', 'en-panel-grid');
            for (const name of Object.keys(this.state.spec.fields)) {
                if (!name.startsWith(prefix) || ['qwen_schedule', 'dit_guidance', 'detail_daemon'].includes(name)) continue;
                this.extraControl(grid, name);
            }
            group.append(grid);
            const notes = {
                qwen: 'Overrides both scheduler selectors. Uses each stage’s steps and actual latent resolution, including after upscale.',
                dit: 'Patches only the unconditional pass. Usually has no effect at CFG 1. Layer indices depend on the model.',
                detail: 'Built in; no additional custom node needed. The detail curve restarts for each stage’s executed schedule.',
            };
            group.append(element('div', 'en-panel-note', notes[key]));
        });
        this.section(content, 'seed', 'Seed', group => {
            this.seed(group);
            if (p.two_stage) {
                const label = element('label', 'en-panel-field'), input = element('input');
                input.type = 'text'; input.inputMode = 'numeric'; input.placeholder = 'Base seed + offset';
                input.value = p.second_seed ?? ''; input.dataset.field = 'second_seed';
                input.oninput = () => this.edit(state => { state.config.parameters.second_seed = input.value; }, false);
                label.append(element('span', '', 'Stage 2 seed (optional)'), input); group.append(label);
                this.number(group, 'seed_offset');
                group.append(element('div', 'en-panel-note', 'Leave Stage 2 seed empty to use base seed + offset (64-bit wrap). An explicit Stage 2 seed takes priority.'));
            }
        });
        if (p.tiled_decode) this.number(content, 'tile_size', 'en-panel-inline');
    }
    extraControl(parent, key) {
        const field = this.state.spec.fields[key], value = this.state.config.parameters[key];
        if (field.options) {
            const control = this.menu.field(parent, field.label, value, field.options,
                next => this.edit(state => { state.config.parameters[key] = next; }));
            control.dataset.field = key; control.title = field.tooltip; return;
        }
        if (typeof field.default === 'boolean') {
            const control = button(field.label, field.tooltip, () => this.edit(state => { state.config.parameters[key] = !value; }));
            control.dataset.field = key; control.setAttribute('aria-pressed', String(value)); parent.append(control); return;
        }
        if (field.text) {
            const label = element('label', 'en-panel-field'), input = element('input');
            input.type = 'text'; input.value = value; input.dataset.field = key; input.title = field.tooltip;
            input.oninput = () => this.edit(state => { state.config.parameters[key] = input.value; }, false);
            label.append(element('span', '', field.label), input); parent.append(label); return;
        }
        this.number(parent, key);
    }
    stageRange(group, second) {
        const numbers = element('div', 'en-panel-grid');
        for (const key of second ? ['second_start', 'second_end'] : ['start_step', 'end_step']) this.number(numbers, key);
        group.append(numbers);
        const toggles = element('div', 'en-panel-grid');
        for (const key of second ? ['second_add_noise', 'second_leftover'] : ['add_noise', 'leftover_noise']) {
            const on = this.state.config.parameters[key];
            const control = button(this.state.spec.fields[key].label, this.state.spec.fields[key].label,
                () => this.edit(state => { state.config.parameters[key] = !on; }));
            control.dataset.field = key; control.setAttribute('aria-pressed', String(on)); toggles.append(control);
        }
        group.append(toggles);
    }
    detailer(content) {
        this.section(content, 'sampler', 'Sampler', group => {
            this.sampling(group, false); this.number(group, 'cycle', 'en-panel-inline');
        });
        this.section(content, 'sizing', 'Sizing', group => {
            const sizes = element('div', 'en-panel-grid');
            this.number(sizes, 'guide_size'); this.number(sizes, 'max_size'); group.append(sizes);
            const control = this.menu.field(group, 'Guide size for', this.state.config.parameters.guide_size_for ? 'Bounding box' : 'Crop region',
                ['Bounding box', 'Crop region'], value => this.edit(state => { state.config.parameters.guide_size_for = value === 'Bounding box'; }));
            control.dataset.field = 'guide_size_for';
        });
        this.section(content, 'mask', 'Mask & blending', group => {
            const numbers = element('div', 'en-panel-grid');
            this.number(numbers, 'feather'); this.number(numbers, 'noise_mask_feather'); group.append(numbers);
        });
        this.section(content, 'seed', 'Seed', group => this.seed(group));
    }
    summary(key) {
        const p = this.state.config.parameters;
        if (this.state.spec.profile === 'advanced') {
            if (key === 'sampler' && p.two_stage) return `${p.sampler_name} · ${p.start_step}–${p.end_step} / ${p.steps}`;
            if (key === 'stage2') return `${p.second_sampler_name} · ${p.second_start}–${p.second_end} / ${p.second_steps}${p.second_start === 0 ? ` · ${p.second_denoise} denoise` : ''}`;
            if (key === 'qwen') return `${p.qwen_dynamic ? 'Dynamic' : 'Fixed'} · terminal ${p.qwen_terminal}`;
            if (key === 'dit') return `Double ${p.dit_double_layers || 'none'} · single ${p.dit_single_layers || 'none'}`;
            if (key === 'detail') return `${p.detail_amount} · ${p.detail_start}–${p.detail_end}`;
            if (key === 'upscale') return `${p.upscale_method} · ${p.upscale_factor}×`;
        }
        if (key === 'sampler') return `${p.sampler_name} · ${p.steps} steps · ${p.denoise} denoise`;
        if (key === 'sizing') return `${p.guide_size_for ? 'BBox' : 'Crop'} ${p.guide_size} · max ${p.max_size}`;
        if (key === 'seed') {
            const seed = this.state.config.seed;
            if (seed.policy === 'random') return 'Random each run';
            const policy = { increment: 'Increment · ', decrement: 'Decrement · ' }[seed.policy] ?? '';
            return `${policy}${seed.value}`;
        }
        return `Blend ${p.feather} · noise ${p.noise_mask_feather}`;
    }
    syncSummaries() {
        const denoise = this.controller.root.querySelector('[data-field="second_denoise"]');
        if (denoise) denoise.disabled = this.state.config.parameters.second_start !== 0;
        for (const label of this.controller.root.querySelectorAll('[data-section-summary]')) {
            label.textContent = label.title = this.summary(label.dataset.sectionSummary);
        }
    }
    section(parent, key, title, build) {
        const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', title);
        const header = element('div', 'en-panel-section-header'), open = this.state.sectionOpen(key);
        const toggle = button('', title, () => this.edit(state => state.toggleSection(key)));
        toggle.className = 'en-panel-section-toggle'; toggle.dataset.field = `section.${key}`;
        toggle.setAttribute('aria-expanded', String(open));
        const summary = element('span', 'en-panel-summary', this.summary(key));
        summary.title = summary.textContent; summary.dataset.sectionSummary = key;
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} ${title}`), summary);
        const pin = button('⌖', `Pin ${title}`, () => this.edit(state => state.togglePin(key)));
        pin.setAttribute('aria-pressed', String(this.state.editor.pins?.[key] === true)); pin.dataset.field = `pin.${key}`;
        header.append(toggle, pin); section.append(header);
        if (open) { const body = element('div', 'en-panel-section-body'); build(body); section.append(body); }
        parent.append(section);
    }
    number(parent, key, className = 'en-panel-field', disabled = false) {
        const field = this.state.spec.fields[key], label = element('label', className);
        const input = element('input'); input.type = 'number'; input.value = this.state.config.parameters[key];
        input.min = field.min; input.max = field.max; input.step = field.step; input.required = true; input.disabled = disabled;
        input.dataset.field = key; input.title = field.tooltip ?? field.label;
        input.oninput = () => this.edit(state => { state.config.parameters[key] = input.value === '' ? null : Number(input.value); }, false);
        label.append(element('span', '', field.label), input); parent.append(label);
    }
    seed(parent) { seedControls(parent, this.controller); }
    dispose() { this.menu.close(); }
}
