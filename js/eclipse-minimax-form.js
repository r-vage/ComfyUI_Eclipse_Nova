/** SPDX-License-Identifier: Apache-2.0
 * Compact MiniMax planning and conditioning controls on the shared themed surface.
 */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { TextFieldSizes } from './eclipse-panel-text-layout.js';

export class MiniMaxForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); this.textSizes = new TextFieldSizes(controller); }
    get state() { return this.controller.state; }
    get p() { return this.state.config.parameters; }
    get kind() { return this.state.config.kind; }
    get ref() { return this.p.conditioning_family === 'ref2va_active_reference'; }
    connected(key) { return this.controller.node.inputs?.some(input => input.name === key && input.link != null); }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    render() {
        this.dispose();
        const { root } = this.controller, focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        const content = element('div', 'en-panel-content');
        if (this.kind.includes('timeline')) this.planner(content);
        else if (this.kind.includes('step')) {
            this.section(content, 'task', 'Task', parent => {
                this.number(parent, 'task_index');
                this.note(parent, 'Connect the planned guide audio and original image sequence. For extensions, use the disk timeline or previous frames.');
            });
        } else this.conditioning(content);
        this.section(content, 'report', 'Report', parent => {
            this.textarea(parent, 'report', 'Last report', this.state.editor.lastReport ?? '', true);
            this.note(parent, 'Last execution. Queue to update after changing inputs or settings.');
        });
        root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[data-field]')].find(el => el.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    planner(parent) {
        this.bar(parent, 'conditioning_family', 'Mode', ['align_to_activity_gap']);
        this.section(parent, 'transitions', 'Transitions', body => {
            if (!this.ref) this.choice(body, 'segment_strategy', 'Strategy');
            else this.note(body, 'Ref2VA uses warm resets with the active original reference.');
            this.number(body, 'warmup_seconds');
            this.textarea(body, 'manual_transition_times');
            this.note(body, 'Comma-separated seconds; blank distributes images evenly. Audio defines the retained 24 FPS timeline.');
        });
        this.section(parent, 'render', 'Render', body => {
            this.number(body, 'max_render_frames');
            if (this.ref) this.choice(body, 'ref_image_size', 'Reference size');
            this.note(body, '124–362 frames in steps of 17. Hidden warmup and endpoints count toward the render limit.');
        });
        this.section(parent, 'technical', 'Technical seams', body => {
            if (!this.ref) {
                this.choice(body, 'technical_split_source', 'Continuity'); this.choice(body, 'reset_anchor', 'Reset anchor');
            }
            if (this.p.technical_split_source === 'original_image_reset') this.choice(body, 'technical_seam_style', 'Seam style');
            this.note(body, this.p.technical_split_source === 'original_image_reset'
                ? 'Long intervals reset from the active original image. Camera-cut instructions apply only to these technical resets.'
                : 'Uses the preceding 22 generated frames at technical seams. Camera-cut instructions are inactive.');
        });
        if (this.p.technical_seam_style === 'intentional_camera_cut') this.section(parent, 'instructions', 'Cut instructions', body => {
            this.textarea(body, 'technical_cut_instruction');
            this.note(body, 'Non-empty lines or connected list entries cycle across technical cuts. Blank uses the default cut instruction.');
        });
        if (this.p.align_to_activity_gap) this.section(parent, 'activity', 'Activity gaps', body => {
            this.choice(body, 'transition_edge', 'Edge');
            const grid = this.grid(body); this.number(grid, 'search_window_seconds'); this.number(grid, 'min_gap_duration');
            if (this.p.transition_edge === 'activity_resume') this.number(grid, 'resume_hold_duration');
            this.note(body, 'Optional Wav2Vec features locate gaps. The guide audio remains separate from this analysis.');
        });
    }
    conditioning(parent) {
        this.bar(parent, 'conditioning_family', 'Mode', !this.ref || this.connected('conditioning_family') ? ['has_start_guide', 'has_last_image'] : []);
        this.section(parent, 'canvas', 'Canvas', body => {
            const grid = this.grid(body); this.number(grid, 'width'); this.number(grid, 'height');
            this.number(body, 'visual_condition_strength');
            if (this.ref || this.connected('conditioning_family')) this.choice(body, 'ref_image_size', 'Reference size');
        });
        this.section(parent, 'prompt', 'Prompts', body => {
            this.number(body, 'prompt_index');
            this.textarea(body, 'prompts');
            this.note(body, 'One complete prompt per non-empty line. An unavailable prompt index uses the first prompt.');
        });
        if (!this.ref || this.connected('conditioning_family')) this.section(parent, 'guides', 'Guides', body => {
            const grid = this.grid(body);
            if (this.p.has_start_guide || this.connected('has_start_guide') || this.connected('start_guide_frame_index')) this.number(grid, 'start_guide_frame_index');
            if (this.p.has_last_image || this.connected('has_last_image') || this.connected('endpoint_frame_index')) this.number(grid, 'endpoint_frame_index');
            this.note(body, 'Use Plan Step’s guide flags and frame positions together. An absent guide has frame index −1. Ref2VA has no positional guides.');
        });
    }
    bar(parent, key, title, toggles = []) {
        const collapsed = this.state.editor.bars?.[key] === true, bar = element('div', 'en-panel-bar');
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', title);
        const disclosure = button('', title, () => this.edit(state => { (state.editor.bars ??= {})[key] = !collapsed; }));
        disclosure.className = 'en-panel-disclosure'; disclosure.dataset.field = `bar.${key}`; disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', `${title}:`));
        if (collapsed) disclosure.append(element('span', 'en-panel-summary', [this.label(key), ...toggles.filter(k => this.p[k] || this.connected(k)).map(k => this.label(k))].join(' · ')));
        bar.append(disclosure);
        if (!collapsed) for (const [field, value, label] of [
            ...Object.entries(this.state.spec.choices[key]).map(([value, label]) => [key, value, label]),
            ...toggles.map(k => [k, !this.p[k], this.state.spec.toggles[k]]),
        ]) {
            const control = button(label, label, () => this.edit(state => state.select(field, value)));
            control.dataset.field = `parameters.${field}.${value}`;
            control.setAttribute('aria-pressed', String(field === key ? this.p[key] === value : this.p[field]));
            control.title = this.state.spec.tips[field] + (this.connected(field) ? ' Connected values take priority when non-None.' : '');
            bar.append(control);
        }
        parent.append(bar);
        if (!collapsed && [key, ...toggles].some(k => this.connected(k))) this.note(parent, 'Connected mode and guide values take priority when non-None. Their local selections are retained.');
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
    inputNote(parent, key) { if (this.connected(key)) this.note(parent, 'Connected input takes priority when non-None; the local value is retained.'); }
    number(parent, key) {
        const field = this.state.spec.numbers[key], label = element('label', 'en-panel-field'), input = element('input');
        input.type = 'number'; input.required = true; input.value = this.p[key] ?? ''; input.dataset.field = `parameters.${key}`;
        for (const name of ['min', 'max', 'step']) input[name] = field[name]; input.title = this.state.spec.tips[key];
        input.oninput = () => this.edit(state => { state.config.parameters[key] = input.value === '' ? null : Number(input.value); }, false);
        label.append(element('span', '', field.label + (this.connected(key) ? ' · Input' : '')), input); parent.append(label);
    }
    choice(parent, key, title) {
        const choices = this.state.spec.choices[key];
        const control = this.menu.field(parent, title, choices[this.p[key]], Object.values(choices), label => {
            const value = Object.keys(choices).find(value => choices[value] === label);
            this.edit(state => state.select(key, value));
        });
        control.dataset.field = `parameters.${key}`; control.title = this.state.spec.tips[key]; this.inputNote(parent, key);
    }
    textarea(parent, key, title = this.state.spec.texts[key]?.[0], value = this.p[key], readOnly = false) {
        const label = element('label', 'en-panel-field'), input = element('textarea');
        input.rows = readOnly ? 5 : key === 'manual_transition_times' ? 2 : 4; input.maxLength = this.state.spec.maxText;
        input.value = value; input.readOnly = readOnly; input.title = this.state.spec.tips[key] ?? title; this.textSizes.attach(input, key);
        if (!readOnly) input.oninput = () => this.edit(state => { state.config.parameters[key] = input.value; }, false);
        label.append(element('span', '', title), input); parent.append(label); this.inputNote(parent, key);
    }
    label(key) {
        if (this.connected(key)) return `${this.state.spec.toggles[key] ?? key.replaceAll('_', ' ')} input`;
        return this.state.spec.choices[key]?.[this.p[key]] ?? this.state.spec.toggles[key] ?? String(this.p[key] ?? '');
    }
    summary(key) {
        if (key === 'canvas') return ['width', 'height'].map(k => this.label(k)).join(' × ');
        if (key === 'transitions') return this.connected('manual_transition_times') ? 'Times input' : this.p.manual_transition_times.trim() ? 'Manual times' : 'Even distribution';
        if (key === 'render') return `${this.p.max_render_frames} frames`;
        if (key === 'activity') return this.label('transition_edge');
        if (key === 'technical') return `${this.label('technical_split_source')} · ${this.label('technical_seam_style')}`;
        if (key === 'guides') return ['has_start_guide', 'has_last_image'].filter(k => this.p[k] || this.connected(k)).map(k => this.label(k)).join(' · ') || 'No guides';
        if (key === 'task') return this.connected('task_index') ? 'Task index input' : `Index ${this.p.task_index}`;
        if (key === 'report') return this.state.editor.lastReport ? 'Last execution' : 'Not run';
        const field = key === 'instructions' ? 'technical_cut_instruction' : 'prompts';
        return this.connected(field) ? 'Connected input' : this.p[field]?.trim() ? 'Local text' : 'Empty';
    }
    syncSummaries() { for (const el of this.controller.root.querySelectorAll('[data-section-summary]')) el.textContent = el.title = this.summary(el.dataset.sectionSummary); }
    dispose() { this.menu.close(); this.textSizes.disconnect(); }
}
