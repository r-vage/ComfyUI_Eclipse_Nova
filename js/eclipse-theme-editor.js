/** Eclipse settings theme editor. Drafts stay local until an explicit save. */
import { element, button } from './eclipse-panel-controls.js';
import { fieldLabel } from './eclipse-theme-editor-controls.js';
import { themeForm, themePreview } from './eclipse-theme-editor-form.js';

let active;
const clone = value => structuredClone(value);
const slug = value => value.toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64);

export function openThemeEditor({ api, selected, onSaved }) {
    if (active?.isConnected) { active.focus(); return; }
    if (!document.getElementById('en-theme-editor-style')) {
        const style = element('link'); style.id = 'en-theme-editor-style'; style.rel = 'stylesheet';
        style.href = new URL('./eclipse-theme-editor.css', import.meta.url).href; document.head.append(style);
    }
    const dialog = element('dialog', 'en-theme-editor'); dialog.setAttribute('aria-label', 'Eclipse Nova theme editor'); active = dialog;
    const form = element('form'); form.noValidate = true;
    const header = element('header'); header.append(element('h2', '', 'Theme editor'), element('span', 'en-theme-format', 'Template format 1'));
    const top = element('div', 'en-theme-top');
    const choose = element('select'); fieldLabel(top, 'Theme', choose);
    const name = element('input'); name.type = 'text'; name.required = true; name.maxLength = 80; fieldLabel(top, 'Theme name', name);
    const body = element('div', 'en-theme-body'), fields = element('div', 'en-theme-editor-fields'); body.append(fields);
    const preview = themePreview(body);
    const footer = element('footer'), status = element('div', 'en-theme-note', 'Loading themes…'); status.setAttribute('role', 'status');
    const saveAs = element('div', 'en-theme-save-as'); saveAs.hidden = true;
    const newName = element('input'); newName.type = 'text'; newName.maxLength = 80; fieldLabel(saveAs, 'New theme name', newName);
    const newId = element('input'); newId.type = 'text'; newId.maxLength = 64; newId.pattern = '[a-z0-9][a-z0-9_-]{0,63}';
    newId.title = 'Lowercase letters, digits, hyphens or underscores. This becomes the filename.'; fieldLabel(saveAs, 'New theme ID', newId);
    let catalog, id, draft, dirty = false, busy = false, closed = false, discardAction;
    const controls = element('div', 'en-theme-editor-controls'); controls.inert = true; controls.append(top, body, saveAs);
    const confirm = element('div', 'en-theme-discard'); confirm.hidden = true;
    confirm.append(element('span', '', 'This theme has unsaved changes.'));
    confirm.append(button('Keep editing', 'Keep editing theme', () => { confirm.hidden = true; discardAction = null; }),
        button('Discard changes', 'Discard theme changes', () => { const action = discardAction; confirm.hidden = true; discardAction = null; action?.(); }));
    function guard(action) { if (dirty) { discardAction = action; confirm.hidden = false; } else action(); }
    function close() { if (busy) return; dialog.close(); }
    const closeButton = button('Close', 'Close theme editor', () => guard(close));
    const revert = button('Revert edits', 'Revert unsaved theme edits', () => load(id));
    const save = button('Save', 'Save theme', () => persist(false)); save.type = 'submit'; save.onclick = null;
    const copy = button('Save As…', 'Save theme as a new template', () => {
        saveAs.hidden = false; newName.value = `${draft.label} copy`.slice(0, 80); newId.value = slug(newName.value);
        delete newId.dataset.edited;
        newName.required = newId.required = true; newName.focus();
    });
    const create = button('Create theme', 'Create theme', () => persist(true));
    const cancelCopy = button('Cancel', 'Cancel Save As', () => { saveAs.hidden = true; newName.required = newId.required = false; });
    saveAs.append(create, cancelCopy);
    newName.oninput = () => { if (!newId.dataset.edited) newId.value = slug(newName.value); };
    newId.oninput = () => { newId.dataset.edited = 'true'; };
    const actions = element('div', 'en-theme-actions'); actions.append(revert, closeButton, copy, save);
    footer.append(confirm, status, actions); form.append(header, controls, footer); dialog.append(form);
    function available() {
        controls.inert = busy || !draft;
        save.disabled = copy.disabled = revert.disabled = busy || !draft;
        closeButton.disabled = busy;
    }
    function changed() {
        dirty = true; status.textContent = 'Unsaved changes · Preview only'; status.classList.remove('en-theme-error'); preview(draft);
    }
    function load(value) {
        id = value; draft = clone(catalog.themes[id]); choose.value = id; name.value = draft.label;
        saveAs.hidden = confirm.hidden = true; newName.required = newId.required = false; delete newId.dataset.edited;
        dirty = false; themeForm(fields, draft, catalog.fields, changed); preview(draft); available();
        status.textContent = `Editing ${draft.label}. Save applies your changes; Save As creates a new theme.`;
        status.classList.remove('en-theme-error');
    }
    function options() {
        choose.replaceChildren();
        for (const [value, theme] of Object.entries(catalog.themes).sort(([, a], [, b]) => a.label.localeCompare(b.label))) {
            const option = element('option', '', `${theme.label} (${value})`); option.value = value; choose.append(option);
        }
    }
    async function request(url, options) {
        const response = await api.fetchApi(`/eclipse-nova/themes/${url}`, options);
        const result = await response.json();
        if (!response.ok || result.success === false) throw Error(result.error || 'Could not read or save the theme.');
        return result;
    }
    async function persist(asNew) {
        if (busy || !draft) return;
        // A failed field inside a collapsed section must be visible/focusable.
        const invalid = [...form.elements].find(input => !input.disabled && input.willValidate && !input.checkValidity());
        if (invalid) { invalid.closest('details')?.setAttribute('open', ''); invalid.reportValidity(); return; }
        const target = asNew ? newId.value : id, value = clone(draft);
        if (asNew) value.label = newName.value;
        busy = true; available(); confirm.hidden = true; status.textContent = 'Saving…';
        try {
            const result = await request('save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: target, theme: value, mode: asNew ? 'create' : 'save', revision: asNew ? null : catalog.revisions[id] }) });
            catalog.themes[target] = result.theme; catalog.revisions[target] = result.revision;
            options(); load(target);
            try { await onSaved(target); status.textContent = `Saved and applied ${value.label}.`; }
            catch (error) { status.textContent = `Theme saved. ${error.message}`; status.classList.add('en-theme-error'); }
        } catch (error) { status.textContent = error.message; status.classList.add('en-theme-error'); }
        finally { busy = false; if (!closed) available(); }
    }
    name.oninput = () => { draft.label = name.value; changed(); };
    choose.onchange = () => { const next = choose.value; choose.value = id; guard(() => load(next)); };
    form.onsubmit = event => { event.preventDefault(); persist(!saveAs.hidden); };
    dialog.oncancel = event => { event.preventDefault(); guard(close); };
    dialog.onkeydown = event => {
        event.stopPropagation();
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); persist(!saveAs.hidden); }
    };
    dialog.onpointerdown = event => event.stopPropagation();
    dialog.addEventListener('wheel', event => event.stopPropagation(), { passive: true });
    dialog.addEventListener('close', () => { closed = true; dialog.remove(); if (active === dialog) active = null; }, { once: true });
    document.body.append(dialog); available(); dialog.showModal();
    request('editor', { cache: 'no-store' }).then(result => {
        if (closed) return;
        catalog = result; if (!Object.keys(catalog.themes).length) throw Error('No valid themes found. Restore a theme file and reopen the editor.');
        options(); load(Object.hasOwn(catalog.themes, selected) ? selected : Object.keys(catalog.themes)[0]);
        if (catalog.errors.length) status.textContent += ` Skipped files: ${catalog.errors.join(' ')}`;
    }).catch(error => { if (!closed) { status.textContent = error.message; status.classList.add('en-theme-error'); } });
}
