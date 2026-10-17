/** Explicit editing of a shared prompt file; drafts never write themselves. */
import { element, button } from './eclipse-panel-controls.js';

export async function openFileEditor(controller, path) {
    controller.closeEditor?.();
    const dialog = element('dialog', 'en-panel en-prompt-dialog'); dialog.setAttribute('aria-label', `Edit ${path}`);
    const content = element('div', 'en-panel-content'), heading = element('strong', '', path); heading.title = path;
    const note = element('div', 'en-panel-note', 'One option per line; long lines scroll horizontally. Saving updates this shared prompt file.');
    const input = element('textarea'); input.setAttribute('aria-label', 'Prompt file content'); input.wrap = 'off'; input.spellcheck = false; input.disabled = true;
    const status = element('div', 'en-panel-note', 'Loading…'); status.setAttribute('role', 'status');
    const actions = element('div', 'en-prompt-actions');
    let revision, closed = false, pending = false, request = 0;
    const close = () => { if (closed) return; closed = true; request++; dialog.close(); dialog.remove(); if (controller.closeEditor === close) controller.closeEditor = null; };
    controller.closeEditor = close;
    const reload = button('Reload file', 'Reload file and discard this draft', async () => {
        const token = ++request; pending = true; save.disabled = reload.disabled = true;
        try {
            const file = await controller.getFile(path);
            if (closed || token !== request) return;
            input.value = file.content; revision = file.revision; input.disabled = false;
            status.textContent = `${file.options.length} options`; input.focus();
        } catch (error) { if (!closed) status.textContent = error.message; }
        finally { if (!closed && token === request) { pending = false; save.disabled = !revision; reload.disabled = false; } }
    });
    const save = button('Save', 'Save prompt file', async () => {
        if (pending || !revision) return;
        pending = true; save.disabled = reload.disabled = true; status.textContent = 'Saving…';
        try {
            const file = await controller.request('/file', { method: 'POST', body: JSON.stringify({ path, revision, content: input.value }) });
            if (controller.disposed) return;
            controller.cacheFile(file); controller.form.render();
            if (!closed) close();
        } catch (error) { if (!closed) status.textContent = error.message; }
        finally { if (!closed) { pending = false; save.disabled = !revision; reload.disabled = false; } }
    });
    save.disabled = true; actions.append(reload, button('Cancel', 'Cancel editing', close), save);
    dialog.oncancel = event => { event.preventDefault(); close(); };
    dialog.onpointerdown = event => event.stopPropagation();
    dialog.onkeydown = event => { event.stopPropagation(); if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); save.click(); } };
    input.oninput = () => { status.textContent = `${input.value.split(/\r?\n/).filter(line => line.trim()).length} options · unsaved`; };
    content.append(heading, note, input, status, actions); dialog.append(content); document.body.append(dialog); dialog.showModal();
    await reload.onclick();
}
