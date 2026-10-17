/** SPDX-License-Identifier: Apache-2.0
 * Explicit compact layouts share controls, without native-widget visibility hooks.
 */
import { app, api } from './comfy/index.js';
import { element, button, SearchMenu } from './eclipse-panel-controls.js';
import { TextFieldSizes } from './eclipse-panel-text-layout.js';
import { createDOMPreview, feedDOMPreview } from './eclipse-dom-preview.js';
import { captureScrollableWheelInVue } from './eclipse-widget-utils.js';

export class OperationForm {
    constructor(controller) {
        this.controller = controller; this.menu = new SearchMenu(); this.textSizes = new TextFieldSizes(controller);
        if (this.layout.preview) {
            this.preview = createDOMPreview(controller.node, { noWidget: true, freeResize: true, minHeight: 80 });
            this.image = controller.node._eclipseDomPreview;
            this.preview.classList.add('en-review-preview-content');
            this.preview.setAttribute('aria-label', 'Segment preview');
            this.preview.style.height = ''; this.preview.style.background = 'var(--en-input-bg)';
            this.image.img.alt = 'Segment preview'; this.image.img.style.width = '100%'; this.image.img.style.height = '100%';
            controller.node.hideOutputImages = true;
        }
    }
    get state() { return this.controller.state; }
    get params() { return this.state.config.parameters; }
    get layout() { return this.state.spec.layout; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    connected(key) { return this.controller.node.inputs?.some(input => input.name === key && input.link != null); }
    visible(condition) {
        if (!condition) return true;
        if (condition.any) return condition.any.some(item => this.visible(item));
        if (condition.all) return condition.all.every(item => this.visible(item));
        const [key, values] = condition;
        // A connected mode is resolved during execution; keep its local controls accessible.
        return this.connected(key) || (values && Object.hasOwn(values, 'not') ? this.params[key] !== values.not
            : Array.isArray(values) ? values.includes(this.params[key]) : this.params[key] === values);
    }
    choiceLabel(value) { return this.state.spec.choiceLabels[value] ?? String(value); }
    render() {
        const { root } = this.controller;
        const focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        this.dispose();
        const content = element('div', 'en-panel-content');
        if (this.layout.annotation) this.annotation(content);
        else if (this.preview) content.append(this.preview);
        else {
            for (const bar of this.layout.bars ?? []) if (this.visible(bar.when)) this.bar(content, bar);
            this.rows(content, this.layout.rows ?? []);
            for (const section of this.layout.sections ?? []) if (this.visible(section.when)) {
                this.section(content, section.key, section.label, body => this.rows(body, section.rows));
            }
            if (this.layout.result) this.section(content, 'result', this.layout.result.label, body => {
                this.textarea(body, 'result', `Last ${this.layout.result.label.toLowerCase()}`, this.state.editor.result ?? '', true);
            });
            if (this.layout.note) content.append(element('div', 'en-panel-note', this.layout.note));
        }
        root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    bar(parent, spec) {
        const collapsed = this.state.editor.bars?.[spec.key] === true, bar = element('div', 'en-panel-bar');
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', spec.label);
        const disclosure = button('', spec.label, () => this.edit(state => { (state.editor.bars ??= {})[spec.key] = !collapsed; }));
        disclosure.className = 'en-panel-disclosure'; disclosure.dataset.field = `bar.${spec.key}`;
        disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', `${spec.label}:`));
        if (collapsed) disclosure.append(element('span', 'en-panel-summary', [
            ...(spec.choice ? [this.connected(spec.choice) ? 'Input' : this.choiceLabel(this.params[spec.choice])] : []),
            ...spec.toggles.filter(key => this.visible(this.layout.when?.[key]) && (this.params[key] || this.connected(key))).map(key => this.state.spec.fields[key].label),
        ].join(' · ') || 'Off'));
        bar.append(disclosure);
        if (!collapsed) {
            if (spec.choice) for (const value of this.state.spec.fields[spec.choice].options) {
                const control = button(this.choiceLabel(value), this.choiceLabel(value), () => this.edit(state => { state.config.parameters[spec.choice] = value; }));
                control.setAttribute('aria-pressed', String(this.params[spec.choice] === value));
                control.dataset.field = `choice.${spec.choice}.${value}`; control.title = this.tip(spec.choice); bar.append(control);
            }
            for (const key of spec.toggles) {
                if (!this.visible(this.layout.when?.[key])) continue;
                const field = this.state.spec.fields[key];
                const control = button(field.label, field.label, () => this.edit(state => { state.config.parameters[key] = !state.config.parameters[key]; }));
                control.setAttribute('aria-pressed', String(this.params[key])); control.dataset.field = `parameters.${key}`;
                control.title = this.tip(key); bar.append(control);
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
        pin.setAttribute('aria-pressed', String(this.state.editor.pins?.[key] === true)); pin.dataset.field = `pin.${key}`;
        header.append(toggle, pin); section.append(header);
        if (open) { const body = element('div', 'en-panel-section-body'); build(body); section.append(body); }
        parent.append(section);
    }
    rows(parent, rows) {
        for (const row of rows) {
            const keys = row.filter(key => this.visible(this.layout.when?.[key])); if (!keys.length) continue;
            const grid = element('div', keys.length > 1 ? 'en-panel-grid' : 'en-panel-operation-row');
            for (const key of keys) this.field(grid, key);
            parent.append(grid);
        }
    }
    tip(key) {
        return (this.state.spec.fields[key].tip || this.state.spec.fields[key].label)
            + (this.connected(key) ? ' Connected non-None input takes priority; local value is retained.' : '');
    }
    field(parent, key) {
        const field = this.state.spec.fields[key], title = field.label + (this.connected(key) ? ' · input' : '');
        if (field.type === 'COMBO') {
            const change = value => this.edit(state => { state.config.parameters[key] = value; });
            const control = this.menu.field(parent, title, this.params[key], field.options, change);
            control.dataset.field = `parameters.${key}`; control.title = this.tip(key);
            if (this.layout.refresh?.includes(key)) {
                control.onclick = () => this.openFreshChoices(control, key, title, change);
                control.onkeydown = event => { if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); this.openFreshChoices(control, key, title, change); } };
            }
        } else if (field.multiline) this.textarea(parent, key, title, this.params[key], false);
        else {
            const label = element('label', 'en-panel-field'), input = element('input');
            const numeric = ['INT', 'FLOAT'].includes(field.type);
            input.type = numeric ? 'number' : 'text'; input.value = this.params[key] ?? '';
            input.dataset.field = `parameters.${key}`; input.title = this.tip(key);
            if (numeric) {
                input.required = true; input.step = field.step ?? (field.type === 'INT' ? 1 : 'any');
                for (const attr of ['min', 'max']) if (field[attr] != null) input[attr] = field[attr];
            }
            input.oninput = () => this.edit(state => { state.config.parameters[key] = numeric ? (input.value === '' ? null : Number(input.value)) : input.value; }, false);
            label.append(element('span', '', title), input); parent.append(label);
        }
    }
    async openFreshChoices(control, key, title, change) {
        if (this.menu.trigger === control) { this.menu.close(true); return; }
        this.request?.abort(); const request = this.request = new AbortController(); control.setAttribute('aria-busy', 'true');
        try {
            const id = this.state.spec.nodeId;
            const response = await api.fetchApi(`/object_info/${encodeURIComponent(id)}`, { signal: request.signal });
            if (!response.ok) throw Error(`Could not refresh models (${response.status}).`);
            const info = await response.json(), field = info[id]?.input?.required?.configuration?.[1]?.editorSpec?.fields?.[key];
            if (request.signal.aborted || !control.isConnected || this.controller.disposed) return;
            if (!Array.isArray(field?.options)) throw Error('Model list unavailable.');
            this.state.spec.fields[key].options = field.options;
            this.menu.open(control, title, this.params[key], field.options, change);
        } catch (error) {
            if (error.name !== 'AbortError' && control.isConnected) {
                const status = element('div', 'en-panel-note', error.message); status.setAttribute('role', 'status'); control.parentElement.append(status);
            }
        } finally { control.removeAttribute('aria-busy'); if (this.request === request) this.request = null; }
    }
    textarea(parent, key, title, value, readOnly) {
        const label = element('label', 'en-panel-field'), input = element('textarea');
        input.rows = readOnly ? 6 : 4; input.value = value; input.readOnly = readOnly;
        this.textSizes.attach(input, key);
        if (!readOnly) { input.title = this.tip(key); input.oninput = () => this.edit(state => { state.config.parameters[key] = input.value; }, false); }
        label.append(element('span', '', title), input); parent.append(label);
    }
    summary(key) {
        if (key === 'result') return this.state.editor.result ? 'Last execution' : 'Not run';
        const fields = this.layout.sections?.find(s => s.key === key)?.rows.flat() ?? [];
        return fields.filter(key => this.visible(this.layout.when?.[key])).map(key => {
            if (this.connected(key)) return `${this.state.spec.fields[key].label} input`;
            if (this.state.spec.fields[key].multiline) return this.params[key]?.trim() ? 'Local text' : 'Empty';
            const value = this.params[key]; return value == null ? 'Unset' : this.choiceLabel(value);
        }).join(' · ');
    }
    syncSummaries() {
        for (const item of this.controller.root.querySelectorAll('[data-section-summary]')) item.textContent = item.title = this.summary(item.dataset.sectionSummary);
    }
    annotation(parent) {
        const bar = element('div', 'en-panel-bar'), editing = this.state.editor.editNote === true;
        const toggle = button(editing ? 'Preview' : 'Edit', editing ? 'Preview note' : 'Edit note', () => this.edit(state => { state.editor.editNote = !editing; }));
        bar.append(toggle); parent.append(bar);
        if (editing) {
            const input = element('textarea', 'en-operation-note'); input.setAttribute('aria-label', 'Markdown note');
            input.value = this.params.text; input.dataset.field = 'note';
            input.oninput = () => this.edit(state => { state.config.parameters.text = input.value; }, false);
            input.onblur = () => queueMicrotask(() => { if (input.isConnected && this.state.editor.editNote) this.edit(state => { state.editor.editNote = false; }); });
            parent.append(input);
        } else {
            const preview = element('div', 'en-operation-note comfy-markdown-content');
            preview.setAttribute('aria-label', 'Markdown note'); preview.tabIndex = 0;
            const render = app.extensionManager?.renderMarkdownToHtml;
            try {
                if (!render) throw Error('Markdown renderer unavailable');
                preview.innerHTML = render.call(app.extensionManager, this.params.text);
            } catch {
                preview.textContent = this.params.text; preview.style.whiteSpace = 'pre-wrap';
            }
            preview.ondblclick = () => { this.edit(state => { state.editor.editNote = true; }); this.controller.root.querySelector('textarea')?.focus(); };
            preview.addEventListener('wheel', event => {
                const max = preview.scrollHeight - preview.clientHeight;
                if ((event.deltaY < 0 && preview.scrollTop > 0) || (event.deltaY > 0 && preview.scrollTop < max - 1)) event.stopPropagation();
            }, { passive: true });
            this.disposeNoteWheel = captureScrollableWheelInVue(preview); parent.append(preview);
        }
    }
    executed(output) {
        if (this.image && output?.images) feedDOMPreview(this.controller.node, output, { publish: false });
        const result = output?.eclipse_operation_result;
        if (Array.isArray(result)) this.edit(state => { state.editor.result = result.join('\n\n'); });
    }
    dispose() {
        this.menu.close(); this.request?.abort(); this.request = null; this.textSizes.disconnect(); this.disposeNoteWheel?.(); this.disposeNoteWheel = null;
    }
    destroy() { this.dispose(); this.image?.dispose(); }
}
