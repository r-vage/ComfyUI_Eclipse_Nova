/** SPDX-License-Identifier: Apache-2.0
 * Conversion, crop and recorder controls on the shared Nova theme.
 */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';

export class MediaToolForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); }
    get state() { return this.controller.state; }
    get params() { return this.state.config.parameters; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    editable(control) { control.dataset.mediaEditable = ''; return control; }
    connected(key) { return this.controller.node.inputs?.some(input => input.name === key && input.link != null); }
    grid(parent) { const grid = element('div', 'en-panel-grid'); parent.append(grid); return grid; }
    note(parent, text) { parent.append(element('div', 'en-panel-note', text)); }
    render() {
        this.dispose();
        const { root } = this.controller, kind = this.state.config.kind;
        const focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        const content = element('div', 'en-panel-content');
        if (kind === 'convert') {
            this.bar(content, 'Conversion', null, ['to_rgb', 'to_grayscale', 'composite_alpha']);
            if (this.params.composite_alpha) this.color(content);
            this.choice(content, 'style', 'Style');
            this.note(content, 'Order: composite alpha → RGB → grayscale → style. Disabled conversions leave the image unchanged.');
        } else if (kind === 'crop') {
            this.bar(content, 'Mirror', 'mirror');
            this.section(content, 'output', 'Output size', body => {
                const size = this.grid(body); this.number(size, 'target_width'); this.number(size, 'target_height');
                const processing = this.grid(body); this.choice(processing, 'divisible_by', 'Divisible by'); this.choice(processing, 'rescale_algorithm', 'Resampling');
                this.choice(body, 'device', 'Device');
                this.note(body, 'Dimensions round up to the selected multiple. 0 disables rounding. Connected width/height take priority when non-None.');
                if (this.params.rescale_algorithm === 'lanczos') this.note(body, 'Tensor processing uses Bicubic for Lanczos.');
            });
            this.section(content, 'framing', 'Framing', body => {
                const grid = this.grid(body); this.number(grid, 'context_expand'); this.number(grid, 'rotation');
                this.note(body, 'Zoom 1 fits the mask; below 1 includes context, above 1 crops closer. Rotation is clockwise. Outside-source pixels stay black and masked.');
            });
            this.section(content, 'mask', 'Mask', body => {
                const grid = this.grid(body); this.number(grid, 'mask_threshold'); this.number(grid, 'mask_blur');
                this.note(body, 'Threshold defines the crop bounds. Blur softens the final mask without changing framing. An empty mask uses the full image.');
            });
        } else {
            this.bar(content, 'Format', 'format', ['strip_start_silence']);
            const deviceRow = element('div', 'en-media-device-row'), field = element('div', 'en-panel-field');
            field.append(element('span', '', 'Output device'));
            const current = this.params.output_device === 'default' ? 'Default' : this.state.editor.deviceLabel || this.params.output_device;
            const trigger = this.editable(button('', 'Output device', () => void this.controller.recorder.openDevices(trigger, this.menu)));
            trigger.className = 'en-panel-select'; trigger.setAttribute('role', 'combobox'); trigger.setAttribute('aria-haspopup', 'listbox'); trigger.setAttribute('aria-expanded', 'false');
            trigger.append(element('span', '', current), element('span', '', '▾')); trigger.title = current;
            trigger.onkeydown = event => { if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); void this.controller.recorder.openDevices(trigger, this.menu); } };
            field.append(trigger); deviceRow.append(field, this.editable(button('↻', 'Refresh devices', () => void this.controller.recorder.openDevices(trigger, this.menu))));
            content.append(deviceRow);
            this.section(content, 'output', 'Output', body => {
                this.text(body, 'filename_prefix', 'Filename prefix');
                if (this.params.format.includes('mp3')) this.choice(body, 'mp3_bitrate', 'MP3 bitrate');
                this.note(body, 'Folder and prefix relative to ComfyUI output. Files receive a unique counter. Capture is 48 kHz stereo.');
            });
            if (this.params.strip_start_silence) this.section(content, 'silence', 'Leading silence', body => {
                this.number(body, 'silence_threshold_db');
                this.note(body, 'Detect activity in 10 ms windows and keep 50 ms before the onset. Update Output reuses the original capture.');
            });
            const actions = element('div', 'en-media-record-actions');
            for (const [key, label] of [['start', 'Start'], ['stop', 'Stop'], ['update', 'Update Output']]) {
                const action = button(label, label, () => void this.controller.recorder[key]()); action.dataset.recorderAction = key; actions.append(action);
            }
            content.append(actions);
            const status = element('div', 'en-media-status'); status.setAttribute('role', 'status');
            this.recorderStatus = element('div'); this.recorderError = element('div', 'en-media-error');
            status.append(this.recorderStatus, this.recorderError); content.append(status);
            this.note(content, 'Start captures and queues the workflow. Stop finalizes audio so downstream nodes can continue.');
        }
        root.replaceChildren(content); this.syncSummaries();
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    bar(parent, title, choiceKey, toggles = []) {
        const collapsed = this.state.editor.collapsed === true, bar = element('div', 'en-panel-bar');
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', title);
        const disclosure = button('', title, () => this.edit(state => { state.editor.collapsed = !collapsed; }));
        disclosure.className = 'en-panel-disclosure'; disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', `${title}:`));
        if (collapsed) {
            const selected = [...(choiceKey ? [this.label(choiceKey, this.params[choiceKey])] : []),
                ...toggles.filter(key => this.params[key]).map(key => this.state.spec.toggles[key])];
            const summary = element('span', 'en-panel-summary', selected.join(' · ') || 'None'); summary.title = summary.textContent; disclosure.append(summary);
        }
        bar.append(disclosure);
        if (!collapsed) {
            if (choiceKey) for (const value of this.state.spec.choices[choiceKey]) {
                const control = this.editable(button(this.label(choiceKey, value), this.label(choiceKey, value), () => this.edit(state => { state.config.parameters[choiceKey] = value; })));
                control.setAttribute('aria-pressed', String(this.params[choiceKey] === value)); bar.append(control);
            }
            for (const key of toggles) {
                const control = this.editable(button(this.state.spec.toggles[key], this.state.spec.toggles[key], () => this.edit(state => { state.config.parameters[key] = !state.config.parameters[key]; })));
                control.setAttribute('aria-pressed', String(this.params[key])); bar.append(control);
            }
        }
        parent.append(bar);
    }
    label(key, value) { return key === 'format' ? value.toUpperCase() : value.replace(/^./, char => char.toUpperCase()); }
    section(parent, key, title, build) {
        const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', title);
        const open = this.state.sectionOpen(key), header = element('div', 'en-panel-section-header');
        const toggle = button('', title, () => this.edit(state => state.toggleSection(key)));
        toggle.className = 'en-panel-section-toggle'; toggle.setAttribute('aria-expanded', String(open));
        const summary = element('span', 'en-panel-summary'); summary.dataset.mediaSummary = key;
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} ${title}`), summary);
        const pin = button('⌖', `Pin ${title}`, () => this.edit(state => state.togglePin(key))); pin.setAttribute('aria-pressed', String(this.state.editor.pins?.[key] === true));
        header.append(toggle, pin); section.append(header);
        if (open) { const body = element('div', 'en-panel-section-body'); build(body); section.append(body); }
        parent.append(section);
    }
    number(parent, key) {
        const spec = this.state.spec.numbers[key], label = element('label', 'en-panel-field'), input = this.editable(element('input'));
        input.type = 'number'; input.required = true; input.value = this.params[key] ?? ''; input.dataset.field = key;
        for (const name of ['min', 'max', 'step']) input[name] = spec[name];
        input.oninput = () => this.edit(state => { state.config.parameters[key] = input.value === '' ? null : Number(input.value); }, false);
        label.append(element('span', '', spec.label), input); parent.append(label);
    }
    text(parent, key, title) {
        const label = element('label', 'en-panel-field'), input = this.editable(element('input'));
        input.type = 'text'; input.value = this.params[key]; input.maxLength = 240; input.dataset.field = key;
        input.oninput = () => this.edit(state => { state.config.parameters[key] = input.value; }, false);
        label.append(element('span', '', title), input); parent.append(label);
    }
    color(parent) {
        const label = element('label', 'en-panel-field'), input = element('input'); input.type = 'color'; input.value = this.params.background_color;
        input.oninput = () => this.edit(state => { state.config.parameters.background_color = input.value; }, false);
        label.append(element('span', '', 'Background color'), input); parent.append(label);
    }
    choice(parent, key, title) {
        const trigger = this.menu.field(parent, title, this.params[key], this.state.spec.choices[key], value => this.edit(state => { state.config.parameters[key] = value; }));
        trigger.dataset.field = key; this.editable(trigger);
    }
    summary(key) {
        const p = this.params;
        if (key === 'output') {
            if (this.state.config.kind === 'recorder') return `${p.filename_prefix} · ${p.format.toUpperCase()}`;
            const divisor = Number(p.divisible_by) || 1;
            return ['target_width', 'target_height'].map(name => this.connected(name) ? `${name === 'target_width' ? 'width' : 'height'} input`
                : Math.ceil(p[name] / divisor) * divisor).join(' × ');
        }
        if (key === 'framing') return `${p.context_expand}× · ${p.rotation}°`;
        if (key === 'mask') return `Threshold ${p.mask_threshold} · Blur ${p.mask_blur}`;
        return `${p.silence_threshold_db} dBFS`;
    }
    syncSummaries() {
        for (const item of this.controller.root.querySelectorAll('[data-media-summary]')) item.textContent = item.title = this.summary(item.dataset.mediaSummary);
        this.syncRecorder();
    }
    syncRecorder() {
        if (this.state.config.kind !== 'recorder') return;
        const session = this.controller.recorder, active = session?.active ?? false, busy = session?.busy ?? false;
        for (const field of this.controller.root.querySelectorAll('[data-media-editable]')) field.disabled = active || busy;
        const enabled = { start: !active, stop: active && session?.state !== 'restoring', update: session?.ready === true };
        for (const control of this.controller.root.querySelectorAll('[data-recorder-action]')) control.disabled = busy || !enabled[control.dataset.recorderAction];
        if (this.recorderStatus) this.recorderStatus.textContent = `${session?.state ?? 'Idle'} · ${Number(session?.elapsed ?? 0).toFixed(1)} s`;
        if (this.recorderError) this.recorderError.textContent = session?.error ?? '';
    }
    dispose() { this.menu.close(); }
}
