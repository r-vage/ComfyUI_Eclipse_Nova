/** Compact Smart Folder sections with the shared Jade controls and Director bars. */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { seedControls } from './eclipse-panel-seed-controls.js';
import { sizeError } from './eclipse-panel-sizing.js';
import { SizeControls } from './eclipse-panel-size-controls.js';

export class FolderForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); }
    get state() { return this.controller.state; }
    get config() { return this.state.config; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    render() {
        this.menu.close(); this.sizeControls?.dispose(); this.sizeControls = null;
        const root = this.controller.root, focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        const content = element('div', 'en-panel-content');
        this.bar(content, 'mode', 'Mode', [['image', 'Image'], ['video', 'Video']], key => this.config.mode === key, key => this.state.mode(key));
        this.bar(content, 'include', 'Include', this.state.features(), key => this.state.enabled(key), key => this.state.toggle(key));
        this.section(content, 'folder', 'Output folder', parent => this.folder(parent));
        if (this.config.size) this.section(content, 'size', this.config.mode === 'image' ? 'Image size' : 'Video size', parent => this.size(parent));
        if (this.config.mode === 'video') {
            this.section(content, 'video', 'Video', parent => {
                const grid = element('div', 'en-panel-grid'); parent.append(grid);
                this.number(grid, 'frame_rate', this.config.video);
                if (this.state.enabled('duration')) this.number(grid, 'duration', this.config.video);
            });
            if (this.config.video.vhs) this.section(content, 'vhs', 'Frame loading', parent => this.vhs(parent));
            if (this.state.enabled('context_length') || this.state.enabled('loop')) this.section(content, 'context', 'Context & loop', parent => {
                const grid = element('div', 'en-panel-grid'); parent.append(grid);
                this.number(grid, 'context_length', this.config.video);
                if (this.config.video.loop) { this.number(grid, 'loop_count', this.config.video.loop); this.number(grid, 'overlap', this.config.video.loop); }
            });
        }
        if (this.config.seed) this.section(content, 'seed', 'Seed', parent => seedControls(parent, this.controller));
        root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    bar(parent, key, title, choices, enabled, change) {
        const bar = element('div', 'en-panel-bar'), collapsed = this.state.editor.bars?.[key] === true;
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', title);
        const toggle = button('', title, () => this.edit(state => { (state.editor.bars ??= {})[key] = !collapsed; }));
        toggle.className = 'en-panel-disclosure'; toggle.dataset.field = `bar.${key}`; toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', `${title}:`));
        if (collapsed) {
            const summary = element('span', 'en-panel-summary', choices.filter(([key]) => enabled(key)).map(([, label]) => label).join(' · ') || 'None');
            summary.title = summary.textContent; toggle.append(summary);
        }
        bar.append(toggle);
        if (!collapsed) for (const [name, label] of choices) {
            const control = button(label, label, () => this.edit(() => change(name)));
            control.dataset.field = `${key}.${name}`; control.setAttribute('aria-pressed', String(enabled(name)));
            if (name === 'context_length' && this.state.enabled('loop')) { control.disabled = true; control.title = 'Loop requires Context.'; }
            bar.append(control);
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
        pin.setAttribute('aria-pressed', String(this.state.editor.pins?.[key] === true)); pin.dataset.field = `pin.${key}`;
        header.append(toggle, pin); section.append(header);
        if (open) { const body = element('div', 'en-panel-section-body'); build(body); section.append(body); }
        parent.append(section);
    }
    summary(key) {
        const c = this.config, v = c.video;
        if (key === 'folder') return `${c.folder.root} · batch ${c.batch_size}`;
        if (key === 'size') return sizeError(c.size, this.state.spec) ? 'Invalid size' : `${c.size.width} × ${c.size.height}`;
        if (key === 'video') return `${v.frame_rate} fps${v.duration != null ? ` · ${v.duration} s` : ''}`;
        if (key === 'context') return `${v.context_length} frames${v.loop ? ` · ${v.loop.loop_count} loops · overlap ${v.loop.overlap}` : ''}`;
        if (key === 'vhs') {
            const cap = v.context_length != null && v.loop?.loop_count > 0 ? v.context_length * v.loop.loop_count : v.vhs.frame_load_cap;
            const count = v.vhs.skip_count;
            const skip = /^(0|[1-9][0-9]{0,19})$/.test(count) && Number.isInteger(v.vhs.skip_first_frames) && Number.isInteger(v.context_length ?? 0)
                ? String(BigInt(v.vhs.skip_first_frames) + BigInt(v.context_length ?? 0) * BigInt(count)) : '?';
            return `${cap === 0 ? 'No cap' : `${cap} frames`} · skip ${skip}`;
        }
        if (key === 'seed') {
            const seed = c.seed;
            return seed.policy === 'random' ? 'Random each run' : `${{ increment: 'Increment · ', decrement: 'Decrement · ' }[seed.policy] ?? ''}${seed.value}`;
        }
        return '';
    }
    syncSummaries() {
        for (const node of this.controller.root.querySelectorAll('[data-section-summary]')) node.textContent = node.title = this.summary(node.dataset.sectionSummary);
        this.sizeControls?.sync();
    }
    input(parent, name, key, value, setter, field = {}) {
        const label = element('label', 'en-panel-field'), input = element('input'); input.type = field.type ?? 'text';
        input.value = value ?? ''; input.dataset.field = key; input.required = true;
        for (const name of ['min', 'max', 'step', 'pattern', 'maxLength', 'inputMode']) if (field[name] != null) input[name] = field[name];
        if (field.title) input.title = field.title;
        input.oninput = () => this.edit(() => setter(input.type === 'number' ? input.value === '' ? null : Number(input.value) : input.value), false);
        label.append(element('span', '', name), input); parent.append(label); return input;
    }
    number(parent, key, owner) {
        const field = this.state.spec.fields[key];
        return this.input(parent, field.label, key, owner[key], value => { owner[key] = value; }, { ...field, type: 'number' });
    }
    choice(parent, label, key, value, choices, setter) {
        const control = this.menu.field(parent, label, value, choices, value => this.edit(() => setter(value)));
        control.dataset.field = key; return control;
    }
    folder(parent) {
        const c = this.config, f = c.folder;
        this.input(parent, 'Root folder', 'folder.root', f.root, value => { f.root = value; }, { maxLength: 1024, title: 'Relative to the ComfyUI output directory. Use / or \\ for nested folders.' });
        if (f.date_time) {
            const grid = element('div', 'en-panel-grid'); parent.append(grid);
            this.input(grid, 'Date/time format', 'folder.date_time.format', f.date_time.format, value => { f.date_time.format = value; }, { maxLength: 1024 });
            this.choice(grid, 'Date/time position', 'folder.date_time.position', f.date_time.position, ['prefix', 'postfix'], value => { f.date_time.position = value; });
        }
        if (f.batch) {
            this.input(parent, 'Batch folder name', 'folder.batch.name', f.batch.name, value => { f.batch.name = value; }, { maxLength: 1024, title: 'Use {} for the number, or {0:03d} for zero padding.' });
            const grid = element('div', 'en-panel-grid'); parent.append(grid);
            this.input(grid, 'Batch number', 'folder.batch.number', f.batch.number, value => { f.batch.number = value; }, { inputMode: 'numeric', pattern: '[1-9][0-9]{0,19}' });
            this.choice(grid, 'After queue', 'folder.batch.policy', f.batch.policy, ['fixed', 'increment'], value => { f.batch.policy = value; });
        }
        this.number(parent, 'batch_size', c);
        if (this.state.editor.lastPath) { const path = element('div', 'en-panel-note en-folder-path', `Last output: ${this.state.editor.lastPath}`); path.title = path.textContent; parent.append(path); }
    }
    vhs(parent) {
        const v = this.config.video, values = v.vhs, grid = element('div', 'en-panel-grid'); parent.append(grid);
        const cap = this.number(grid, 'frame_load_cap', values);
        if (v.context_length != null && v.loop?.loop_count > 0) { cap.disabled = true; cap.title = 'Calculated from Context length × Loop count.'; }
        this.number(grid, 'select_every_nth', values); this.number(grid, 'skip_first_frames', values);
        if (v.context_length != null) {
            this.input(grid, 'Skip contexts', 'video.vhs.skip_count', values.skip_count, value => { values.skip_count = value; }, { inputMode: 'numeric', pattern: '(0|[1-9][0-9]{0,19})' });
            this.choice(grid, 'After queue', 'video.vhs.skip_policy', values.skip_policy, ['fixed', 'increment'], value => { values.skip_policy = value; });
        }
        parent.append(element('div', 'en-panel-note', 'A frame load cap of 0 means no limit. Context skips add Context length × Skip contexts to Skip first frames.'));
    }
    size(parent) { this.sizeControls = new SizeControls(this.controller, parent); }
    dispose() { this.menu.close(); this.sizeControls?.dispose(); }
}
