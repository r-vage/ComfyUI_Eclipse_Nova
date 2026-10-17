/** Smart Prompt folders, file pickers and results on the shared Nova surface. */
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { seedControls } from './eclipse-panel-seed-controls.js';
import { openFileEditor } from './eclipse-smart-prompt-editor.js';
import { PromptRowDrag } from './eclipse-smart-prompt-drag.js';
import { runActions } from './eclipse-panel-run.js';

const choiceKey = choice => JSON.stringify(choice.mode === 'value' ? { mode: 'value', value: choice.value } : { mode: choice.mode });
const choiceLabel = key => {
    const item = JSON.parse(key);
    return item.mode === 'none' ? 'None' : item.mode === 'random' ? 'Random' : ['None', 'Random'].includes(item.value) ? `${item.value} (text)` : item.value;
};

export class PromptForm {
    constructor(controller) { this.controller = controller; this.menu = new SearchMenu(); this.drag = new PromptRowDrag(); this.request = 0; }
    get state() { return this.controller.state; }
    get catalog() { return this.controller.catalog; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    render() {
        this.request++; this.menu.close(); this.drag.cancel();
        const root = this.controller.root, focused = root.contains(document.activeElement) ? document.activeElement?.dataset.field : null;
        const content = element('div', 'en-panel-content');
        this.bar(content);
        if (this.controller.message) { const note = element('div', 'en-panel-note', this.controller.message); note.setAttribute('role', 'status'); content.append(note); }
        const active = this.state.folderOrder(this.catalog).filter(id => this.state.folder(id));
        for (const [index, id] of active.entries()) this.section(content, `folder:${id}`, id,
            `${this.state.selections(id).length} selected${this.catalog.folders.some(f => f.id === id) ? '' : ' · missing folder'}`,
            body => this.folder(body, id), header => {
                this.arrows(header, 'folder', id, index, active.length, delta => this.edit(state => state.moveFolder(id, delta, this.catalog)));
                const reset = button('↶', `Reset ${id}`, () => this.edit(state => state.reset(id))); reset.className = 'en-prompt-icon'; header.append(reset);
            });
        if (!active.length) content.append(element('div', 'en-panel-note', 'Select folders to build your prompt.'));
        this.section(content, 'result', 'Result', this.state.editor.lastResult === undefined ? 'Run to preview' : 'Last execution', body => {
            const output = element('textarea'); output.readOnly = true; output.value = this.state.editor.lastResult ?? '';
            output.setAttribute('aria-label', 'Last generated prompt'); output.rows = 4; body.append(output);
            const copy = button('Copy', 'Copy generated prompt', async () => {
                try { await navigator.clipboard.writeText(output.value); copy.textContent = 'Copied'; }
                catch { output.select(); copy.textContent = 'Select and copy'; }
            }); copy.disabled = !output.value; body.append(copy);
        });
        if (this.state.config.seed.source === 'local') this.section(content, 'seed', 'Seed', this.seedSummary(), body => seedControls(body, this.controller));
        root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    bar(parent) {
        const state = this.state, collapsed = state.editor.barCollapsed === true, bar = element('div', 'en-panel-bar en-prompt-bar');
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Folders');
        const disclosure = button('', 'Folders', () => this.edit(s => { s.editor.barCollapsed = !collapsed; }));
        disclosure.className = 'en-panel-disclosure'; disclosure.dataset.field = 'folders'; disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Folders:'));
        if (collapsed) disclosure.append(element('span', 'en-panel-summary', `${state.config.folders.map(f => f.id).join(' · ') || 'None'} · ${state.config.seed.source === 'local' ? 'Local seed' : 'Input seed'}`));
        bar.append(disclosure);
        const actions = element('div', 'en-prompt-bar-actions'); actions.setAttribute('role', 'group'); actions.setAttribute('aria-label', 'Prompt controls');
        if (!collapsed) {
            const refresh = button('↻', 'Refresh prompt files', () => this.controller.refresh()); refresh.disabled = this.controller.loading; refresh.className = 'en-prompt-icon';
            actions.append(refresh);
        }
        const reset = button('↶', 'Reset selected folders', () => this.edit(s => s.reset())); reset.className = 'en-prompt-icon'; actions.append(reset);
        if (!collapsed) {
            for (const id of state.folderOrder(this.catalog)) {
                const exists = this.catalog.folders.some(f => f.id === id);
                const control = button(id, `Include ${id}`, () => this.edit(s => s.toggleFolder(id, this.catalog)));
                control.dataset.field = `folder.${id}`; control.setAttribute('aria-pressed', String(!!state.folder(id)));
                if (!exists) control.title = `${id} (missing folder; selections retained)`;
                bar.append(control);
            }
            const local = state.config.seed.source === 'local', seed = button('Local seed', 'Local seed', () => this.edit(s => s.setLocalSeed(!local, this.controller.connected())));
            seed.dataset.field = 'seed.source'; seed.setAttribute('aria-pressed', String(local)); seed.className = 'en-prompt-seed-source';
            seed.disabled = local && !this.controller.connected();
            seed.title = seed.disabled ? 'Connect seed_input to use an external seed.' : local ? 'Local seed is active; seed_input is ignored.' : 'seed_input is active; enable to use the local seed.';
            actions.append(seed);
        }
        actions.append(runActions(this.controller, { beforeRun: () => {
            if (!this.state.sectionOpen('result')) this.edit(state => state.openSection('result'));
        } }));
        bar.append(actions);
        parent.append(bar);
    }
    seedSummary() {
        const seed = this.state.config.seed;
        return seed.policy === 'random' ? 'Random each run' : `${{ increment: 'Increment · ', decrement: 'Decrement · ' }[seed.policy] ?? ''}${seed.value}`;
    }
    syncSummaries() { const label = this.controller.root.querySelector('[data-seed-summary]'); if (label) label.textContent = this.seedSummary(); }
    section(parent, key, title, summary, build, actions = null) {
        const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', title); section.dataset.section = key;
        const header = element('div', 'en-panel-section-header'), open = this.state.sectionOpen(key);
        const toggle = button('', title, () => this.edit(state => state.toggleSection(key))); toggle.className = 'en-panel-section-toggle';
        toggle.dataset.field = `section.${key}`; toggle.setAttribute('aria-expanded', String(open));
        const description = element('span', 'en-panel-summary', summary); description.title = summary; if (key === 'seed') description.dataset.seedSummary = '';
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} ${title}`), description); header.append(toggle);
        actions?.(header);
        const pin = button('⌖', `Pin ${title}`, () => this.edit(state => state.togglePin(key))); pin.setAttribute('aria-pressed', String(this.state.editor.pins?.[key] === true)); pin.dataset.field = `pin.${key}`;
        header.append(pin); section.append(header);
        if (open) { const body = element('div', 'en-panel-section-body'); build(body); section.append(body); }
        parent.append(section);
    }
    arrows(parent, kind, id, index, length, move) {
        const group = element('div', 'en-prompt-order');
        for (const [delta, direction, glyph] of [[-1, 'up', '↑'], [1, 'down', '↓']]) {
            const arrow = button(glyph, `Move ${kind} ${id} ${direction}`, () => move(delta)); arrow.disabled = delta < 0 ? index === 0 : index === length - 1; group.append(arrow);
        }
        parent.append(group);
    }
    folder(parent, id) {
        parent.classList.add('en-prompt-files');
        const paths = this.state.fileOrder(id, this.catalog), available = this.catalog.folders.find(f => f.id === id)?.files ?? [];
        for (const [index, path] of paths.entries()) {
            const meta = available.find(f => f.id === path), name = meta?.name ?? path.split('/').at(-1).replace(/\.txt$/i, '');
            const row = element('div', 'en-prompt-file'); row.dataset.file = path;
            const field = element('div', 'en-panel-field'), selection = this.state.selection(id, path), key = choiceKey(selection), file = this.controller.files.get(path);
            const missing = selection.mode !== 'none' && (!meta || (selection.mode === 'value' && file && !file.options.includes(selection.value)));
            const label = element('span', 'en-prompt-drag-handle', `${name}${!meta ? ' · missing file' : ''}:`);
            label.title = `${path}${!meta ? ' (missing file)' : ''}\nDrag to reorder within this folder.`;
            label.onpointerdown = event => {
                this.request++; this.menu.close();
                this.drag.start(event, row, delta => this.edit(state => state.moveFile(id, path, delta, this.catalog)));
            };
            field.append(label);
            const trigger = button('', `Choose ${path}`, () => this.pick(trigger, id, path, key)); trigger.className = 'en-panel-select';
            trigger.dataset.field = path; trigger.setAttribute('role', 'combobox'); trigger.setAttribute('aria-expanded', 'false'); trigger.setAttribute('aria-haspopup', 'listbox');
            trigger.title = `${path}\n${choiceLabel(key)}${missing ? ' (unavailable)' : ''}`;
            trigger.append(element('span', missing ? 'en-panel-error' : '', `${choiceLabel(key)}${missing ? ' (unavailable)' : ''}`), element('span', '', '▾'));
            trigger.onkeydown = event => { if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); this.pick(trigger, id, path, key); } };
            field.append(trigger); row.append(field);
            this.arrows(row, 'file', path, index, paths.length, delta => this.edit(state => state.moveFile(id, path, delta, this.catalog)));
            const edit = button('✎', `Edit ${path}`, () => openFileEditor(this.controller, path)); edit.className = 'en-prompt-icon'; edit.disabled = !meta; row.append(edit);
            parent.append(row);
        }
    }
    async pick(trigger, folder, path, current) {
        if (this.menu.trigger === trigger) { this.menu.close(true); return; }
        const token = ++this.request;
        try {
            const file = await this.controller.getFile(path);
            if (this.controller.disposed || token !== this.request || !trigger.isConnected) return;
            const options = [choiceKey({ mode: 'none' }), choiceKey({ mode: 'random' }), ...[...new Set(file.options)].map(value => choiceKey({ mode: 'value', value }))];
            this.menu.open(trigger, path, current, options, value => this.edit(state => state.setSelection(folder, path, JSON.parse(value), this.catalog)), choiceLabel);
        } catch (error) {
            if (this.controller.disposed || token !== this.request || !trigger.isConnected) return;
            // Missing choices stay visible and can still be explicitly cleared.
            this.controller.message = error.message;
            this.menu.open(trigger, path, current, [choiceKey({ mode: 'none' })], value => this.edit(state => state.setSelection(folder, path, JSON.parse(value), this.catalog)), choiceLabel);
        }
    }
    dispose() { this.request++; this.menu.close(); this.drag.cancel(); }
}
