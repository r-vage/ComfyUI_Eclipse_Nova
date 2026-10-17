/** Paths-only source editor with Single/Range/Step and conditional sections. */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { postJSON } from './eclipse-image-loader-api.js';
import { ResizeState } from './eclipse-resize-state.js';
import { ResizeForm } from './eclipse-resize-form.js';

export class LoadFilesForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); this.status = ''; this.request = 0; }
    get state() { return this.controller.state; }
    get config() { return this.state.config; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    connected(name) { return this.controller.node.inputs?.some(input => input.name === name && input.link != null); }
    sourceKey() { return JSON.stringify([this.config.paths, this.config.recursive, this.config.sort, this.config.revision]); }
    async loadCatalog(refresh = false) {
        const key = this.sourceKey(), request = ++this.request; this.catalogKey = key;
        if (!this.config.paths.trim()) { this.total = null; this.status = ''; this.syncSummaries(); return; }
        try {
            const data = await postJSON('/eclipse-nova/load_files/catalog', { configuration: this.state.value(), refresh });
            if (this.dead || request !== this.request || key !== this.sourceKey()) return;
            this.total = data.total; this.status = `${data.total} frames · ${data.files} files`; this.syncSummaries();
        } catch (error) { if (!this.dead && request === this.request) { this.total = null; this.status = error.message; this.syncSummaries(); } }
    }
    render() {
        this.dispose();
        const content = element('div', 'en-panel-content');
        this.bar(content, 'selection', 'Selection', Object.entries(this.state.spec.choices.mode), key => this.config.mode === key,
            key => this.edit(state => { state.config.mode = key; state.openSection('selection'); }));
        const options = [['recursive', 'Subfolders'], ['metadata', 'Metadata'], ['resize', 'Resize'], ['stop_at_end', 'Stop at end']];
        this.bar(content, 'options', 'Options', options, key => !!this.config[key], key => this.edit(state => {
            if (key === 'resize') state.toggleResize(); else state.config[key] = !state.config[key];
        }));
        const label = element('label', 'en-panel-field'), paths = element('textarea'); paths.value = this.config.paths;
        paths.rows = 3; paths.placeholder = 'One image, video or folder path per line'; paths.dataset.field = 'paths';
        paths.oninput = () => this.edit(state => { state.config.paths = paths.value; }, false);
        paths.onchange = () => void this.loadCatalog(); label.append(element('span', '', 'Files / folders'), paths); content.append(label);
        const count = element('div', 'en-loader-actions'); this.statusElement = element('span', 'en-panel-note'); this.statusElement.setAttribute('role', 'status');
        count.append(this.statusElement, button('↻', 'Refresh source', () => {
            this.edit(state => { state.config.revision++; }, false); void this.loadCatalog(true);
        })); content.append(count);
        this.section(content, 'selection', 'Selection'); this.section(content, 'sorting', 'Sorting');
        if (this.config.resize) this.section(content, 'resize', 'Resize');
        this.controller.root.replaceChildren(content); this.syncSummaries(); this.controller.measure();
        if (this.catalogKey !== this.sourceKey()) void this.loadCatalog();
    }
    bar(parent, key, title, options, selected, change) {
        const collapsed = this.state.editor.bars?.[key] === true, bar = element('div', 'en-panel-bar');
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', title);
        const toggle = button('', title, () => this.edit(state => { (state.editor.bars ??= {})[key] = !collapsed; }));
        toggle.className = 'en-panel-disclosure'; toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', title + ':'));
        if (collapsed) toggle.append(element('span', 'en-panel-summary', options.filter(([name]) => selected(name)).map(([, label]) => label).join(' · ') || 'None'));
        bar.append(toggle);
        if (!collapsed) for (const [name, label] of options) { const control = button(label, label, () => change(name)); control.setAttribute('aria-pressed', String(selected(name))); bar.append(control); }
        parent.append(bar);
    }
    section(parent, key, title) {
        const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', title);
        const header = element('div', 'en-panel-section-header'), open = this.state.sectionOpen(key);
        const toggle = button('', title, () => this.edit(state => state.toggleSection(key))); toggle.className = 'en-panel-section-toggle';
        toggle.setAttribute('aria-expanded', String(open));
        const summary = element('span', 'en-panel-summary', this.summary(key)); summary.dataset.sectionSummary = key;
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} ${title}`), summary);
        const pin = button('⌖', `Pin ${title}`, () => this.edit(state => state.togglePin(key))); pin.setAttribute('aria-pressed', String(!!this.state.editor.pins?.[key]));
        header.append(toggle, pin); section.append(header);
        if (open) { const body = element('div', 'en-panel-section-body'); this.body(body, key); section.append(body); }
        parent.append(section);
    }
    grid(parent) { const row = element('div', 'en-panel-grid'); parent.append(row); return row; }
    number(parent, group, key, title) {
        const label = element('label', 'en-panel-field'), input = element('input'); input.type = 'number'; input.required = true;
        input.value = this.config[group][key] ?? ''; input.dataset.field = `${group}.${key}`;
        for (const name of ['min', 'max', 'step']) input[name] = this.state.spec.index[name];
        input.title = title;
        input.oninput = () => this.edit(state => { state.config[group][key] = input.value === '' ? null : Number(input.value); }, false);
        label.append(element('span', '', title), input); parent.append(label);
    }
    choice(parent, group, key, title, choices) {
        return this.menu.field(parent, title, choices[this.config[group][key]], Object.values(choices), label => {
            this.edit(state => { state.config[group][key] = Object.keys(choices).find(key => choices[key] === label); });
        });
    }
    body(parent, key) {
        const choices = this.state.spec.choices;
        if (key === 'selection') {
            const row = this.grid(parent);
            if (this.config.mode === 'single') {
                this.number(row, 'single', 'index', 'Index');
                this.choice(row, 'single', 'advance', 'After run', choices.advance);
                parent.append(element('div', 'en-panel-note', this.connected('seed_input') ? 'Advance once when seed_input changes; repeat the same frame while it stays unchanged.'
                        : 'Index is the starting frame. Advancement runs only when the node executes.'));
            } else {
                this.number(row, 'range', 'start', 'Start'); this.number(row, 'range', 'end', 'End');
                parent.append(element('div', 'en-panel-note', 'End is inclusive. −1 means the last frame.'));
                if (this.config.mode === 'step') {
                    const step = this.grid(parent); this.number(step, 'step', 'batch_index', 'Batch index');
                    this.choice(step, 'step', 'advance', 'After run', choices.step_advance);
                    parent.append(element('div', 'en-panel-note', 'Start 0, end 7, batch index 2 selects frames 16–23.'));
                }
            }
            this.resultElement = element('div', 'en-panel-note', this.resultText()); parent.append(this.resultElement);
        } else if (key === 'sorting') {
            const row = this.grid(parent); this.choice(row, 'sort', 'by', 'Sort by', choices.sort_by); this.choice(row, 'sort', 'order', 'Order', choices.sort_order);
            parent.append(element('div', 'en-panel-note', 'Sort within each folder; keep path-line order. Folders discover images; add videos as explicit paths.'));
        } else if (key === 'resize') {
            this.choice(parent, 'resize', 'policy', 'Size policy', choices.resize_policy);
            const connected = ['width', 'height'].filter(name => this.connected(name));
            if (connected.length) {
                const target = this.config.resize.settings.scale_to, label = this.state.spec.resize.choices.scale_to[target];
                let text = `Connected ${connected.join(' / ')} is ignored unless Size policy is Custom.`;
                if (this.config.resize.policy === 'custom') {
                    if (target === 'custom') text = `Connected ${connected.join(' / ')} takes priority when non-None. Panel values remain available otherwise.`;
                    else if (['longest', 'shortest'].includes(target)) text = `${label} uses the ${target === 'longest' ? 'larger' : 'smaller'} connected dimension, or the only value. None uses the panel size.`;
                    else if (connected.includes(target)) text = `Connected ${target} sets the target ${target} when non-None. Otherwise, the panel size is used.`;
                    else text = `Connected ${connected.join(' / ')} is unused with Target ${label}.`;
                }
                const note = element('div', 'en-panel-note', text);
                note.setAttribute('role', 'status'); parent.append(note);
            }
            if (this.config.resize.policy !== 'custom') return;
            const resize = new ResizeState(JSON.stringify(this.config.resize.settings), this.state.spec.resize, this.state.editor.resizeEditor ?? {});
            const adapter = { node: this.controller.node, state: resize, edit: (fn, render = true) => this.edit(state => {
                fn(resize); state.config.resize.settings = resize.config; state.editor.resizeEditor = resize.editor;
            }, render) };
            const form = this.resizeForm = new ResizeForm(adapter);
            const row = this.grid(parent); form.choice(row, 'scale_to', 'Target');
            if (resize.config.scale_to !== 'custom') form.choice(row, 'aspect_ratio', 'Aspect');
            const dimensions = this.grid(parent);
            for (const name of resize.config.scale_to === 'custom' ? ['custom_width', 'custom_height'] : ['size']) {
                const input = form.number(dimensions, name);
                if (name !== 'size') input.title = 'Target pixels; 0 keeps the source dimension. A connected non-None input takes priority.';
            }
            const fitting = this.grid(parent); form.choice(fitting, 'fit', 'Fit'); form.choice(fitting, 'method', 'Method');
            if (Object.hasOwn(resize.config, 'crop_position')) form.choice(parent, 'crop_position', 'Position');
            if (resize.config.fit === 'pad') {
                const label = element('label', 'en-panel-field'), color = element('input'); color.type = 'color'; color.value = resize.config.pad_color;
                color.oninput = () => adapter.edit(state => { state.config.pad_color = color.value; }, false);
                label.append(element('span', '', 'Padding color'), color); parent.append(label);
            }
            const processing = this.grid(parent); form.number(processing, 'divisible_by'); form.choice(processing, 'device', 'Device');
        }
    }
    resultText() {
        if (!this.info) return '';
        if (this.info.stopped) return 'End reached — downstream execution blocked.';
        const { start, end, total } = this.info;
        const selection = start === end ? start : `${start}–${end}`;
        return `Last selection: ${selection} of ${total} frames`;
    }
    summary(key) {
        if (key === 'selection') return this.resultText() || this.state.spec.choices.mode[this.config.mode];
        if (key === 'sorting') return `${this.state.spec.choices.sort_by[this.config.sort.by]} · ${this.config.sort.order}`;
        if (key === 'resize') return this.state.spec.choices.resize_policy[this.config.resize.policy];
    }
    executed(data) { this.info = data.eclipse_loader?.[0]; this.syncSummaries(); this.controller.measure(); }
    syncSummaries() {
        if (this.statusElement) this.statusElement.textContent = this.status;
        if (this.resultElement) this.resultElement.textContent = this.resultText();
        for (const el of this.controller.root.querySelectorAll('[data-section-summary]')) el.textContent = el.title = this.summary(el.dataset.sectionSummary);
    }
    dispose() { this.menu.close(); this.resizeForm?.dispose(); this.resizeForm = null; }
    destroy() { this.dead = true; this.request++; this.dispose(); }
}
