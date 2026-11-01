/** Explicit named recipes for every Advanced Sampler mode. */
import { api } from './comfy/index.js';
import { element, button } from './eclipse-panel-controls.js';

async function request(path, body) {
    const response = await api.fetchApi(`/eclipse-nova/sampler/${path}`, body === undefined ? {} : {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    let data;
    try { data = await response.json(); }
    catch { throw Error('Sampler presets are unavailable. Restart ComfyUI and refresh the page.'); }
    if (!response.ok) throw Error(data.error || 'Sampler preset request failed.');
    return data;
}

export class SamplerPresets {
    constructor(controller) { this.controller = controller; }
    bar(parent) {
        const controller = this.controller, editor = controller.state.editor;
        const bar = element('div', 'en-panel-bar en-sampler-preset-bar'), collapsed = editor.presetCollapsed === true;
        bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Presets'); bar.dataset.collapsed = String(collapsed);
        const title = button('', 'Presets', () => controller.edit(state => { state.editor.presetCollapsed = !collapsed; }));
        title.className = 'en-panel-disclosure'; title.dataset.field = 'presets'; title.setAttribute('aria-expanded', String(!collapsed));
        title.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Presets:'));
        const current = editor.presetName || 'Current configuration';
        if (collapsed) { const summary = element('span', 'en-panel-summary', current); summary.title = current; title.append(summary); }
        bar.append(title);
        if (!collapsed) {
            const picker = button(current, 'Load sampler preset', () => this.open());
            picker.className = 'en-preset-picker'; picker.title = current; picker.setAttribute('aria-haspopup', 'dialog');
            bar.append(picker, button('Save…', 'Save sampler preset', () => this.open(true)));
        }
        parent.append(bar);
    }
    open(saving = false) {
        this.close();
        const controller = this.controller;
        const dialog = element('dialog', 'en-panel en-prompt-dialog en-sampler-preset-dialog');
        dialog.setAttribute('aria-label', 'Sampler presets');
        const content = element('div', 'en-panel-content'), heading = element('div', 'en-preset-heading');
        const close = button('Close', 'Close sampler presets', () => this.close()); close.dataset.presetClose = 'true';
        heading.append(element('strong', '', 'Sampler presets'), close);
        const note = element('div', 'en-panel-note', 'Includes sampling modes, both stages, denoise, latent upscale and optional guidance. Seeds, pipe overrides, decode and preview stay with this node.');
        const name = element('input'); name.maxLength = 128; name.setAttribute('aria-label', 'Preset name');
        name.value = controller.state.editor.presetName || ''; name.placeholder = 'Model or setup name';
        const nameLabel = element('label', 'en-panel-field'); nameLabel.append(element('span', '', 'Preset name'), name);
        const overwrite = element('input'); overwrite.type = 'checkbox';
        const overwriteLabel = element('label', 'en-preset-overwrite'); overwriteLabel.append(overwrite, document.createTextNode(' Overwrite existing preset'));
        const search = element('input'); search.type = 'search'; search.placeholder = 'Search presets…'; search.setAttribute('aria-label', 'Search presets');
        const results = element('div', 'en-preset-results'); results.setAttribute('aria-label', 'Saved sampler presets');
        const count = element('div', 'en-panel-note'), status = element('div', 'en-panel-note'); status.setAttribute('role', 'status');
        let names = [], busy = false, confirming = null, limit = 100;
        const active = () => this.dialog === dialog && !controller.disposed;
        const render = () => {
            if (!active()) return;
            const existing = names.includes(name.value.trim());
            overwriteLabel.hidden = !existing;
            save.disabled = busy || !name.value.trim() || (existing && !overwrite.checked);
            results.replaceChildren();
            const shown = names.filter(value => value.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()));
            count.textContent = `${shown.length} ${shown.length === 1 ? 'preset' : 'presets'}`;
            if (!names.length) results.append(element('div', 'en-panel-note', 'Save your current settings to create a preset.'));
            for (const value of shown.slice(0, limit)) {
                const row = element('div', 'en-preset-row'); row.dataset.name = value;
                if (confirming === value) {
                    row.append(element('span', 'en-preset-delete-name', `Delete “${value}”?`),
                        button('Delete', `Confirm delete ${value}`, () => run(async () => {
                            const data = await request('preset/delete', { name: value });
                            if (!active()) return;
                            names = data.presets; confirming = null; overwrite.checked = false;
                            if (name.value === value) name.value = '';
                            if (controller.state.editor.presetName === value) controller.edit(state => { delete state.editor.presetName; });
                            status.textContent = 'Preset deleted.';
                        })), button('Cancel', 'Cancel deletion', () => { confirming = null; render(); }));
                } else {
                    const load = button(value, `Load ${value}`, () => run(async () => {
                        const revision = controller.revision;
                        const preset = await request(`preset?${new URLSearchParams({ name: value })}`);
                        if (!active()) return;
                        if (revision !== controller.revision) throw Error('The sampler changed while loading. Select the preset again to apply it.');
                        controller.edit(() => { controller.state = controller.state.withPreset(preset, value); });
                        this.close();
                    }));
                    load.className = 'en-preset-picker'; load.title = value;
                    load.setAttribute('aria-current', String(controller.state.editor.presetName === value));
                    row.append(load, button('×', `Delete ${value}`, () => { confirming = value; render(); }));
                }
                results.append(row);
            }
            if (shown.length > limit) results.append(button('Show more', 'Show more presets', () => { limit += 100; render(); }));
        };
        const run = async task => {
            if (busy || !active()) return;
            busy = true; status.textContent = '';
            for (const control of dialog.querySelectorAll('input, button')) if (!control.dataset.presetClose) control.disabled = true;
            try { await task(); }
            catch (error) { if (active()) status.textContent = error.message; }
            finally {
                busy = false;
                if (active()) {
                    for (const control of dialog.querySelectorAll('input, button')) control.disabled = false;
                    render();
                }
            }
        };
        const save = button('Save preset', 'Save preset', () => run(async () => {
            const selected = name.value.trim(), revision = controller.revision;
            const preset = controller.state.preset();
            await request('preset', { name: selected, preset, overwrite: overwrite.checked });
            if (!active()) return;
            if (revision === controller.revision) controller.edit(state => { state.editor.presetName = selected; });
            this.close();
        }));
        const refresh = async () => {
            const data = await request('presets');
            if (active()) names = data.presets;
        };
        const saveRow = element('div', 'en-preset-save'); saveRow.append(nameLabel, save);
        const searchRow = element('div', 'en-preset-search');
        searchRow.append(search, button('↻', 'Refresh presets', () => run(refresh)));
        name.oninput = () => { overwrite.checked = false; render(); };
        overwrite.onchange = render;
        search.oninput = () => { limit = 100; confirming = null; render(); };
        content.append(heading, note);
        if (controller.state.config.parameters.allow_overwrite) content.append(element('div', 'en-panel-note', 'Use pipe settings is enabled: supplied pipe values still take priority.'));
        content.append(saveRow, overwriteLabel, searchRow, count, results, status); dialog.append(content);
        dialog.oncancel = event => { event.preventDefault(); this.close(); };
        dialog.onpointerdown = event => event.stopPropagation(); dialog.onkeydown = event => event.stopPropagation();
        this.dialog = dialog; document.body.append(dialog); dialog.showModal(); render();
        run(refresh).then(() => { if (active()) { (saving ? name : search).focus(); if (saving) name.select(); } });
    }
    close() {
        const dialog = this.dialog; this.dialog = null;
        if (dialog) { dialog.close(); dialog.remove(); }
    }
    dispose() { this.close(); }
}
