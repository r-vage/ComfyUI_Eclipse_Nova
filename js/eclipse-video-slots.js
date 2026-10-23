/** Per-clip slot controls for the Nova video panel. Copyright (c) 2026 r-vage. Apache-2.0. */
import { button, element } from './eclipse-panel-controls.js';
import { captureScrollableWheelInVue } from './eclipse-widget-utils.js';

export function createVideoSlots(actions) {
    const root = element('section', 'en-video-slots'); root.setAttribute('aria-label', 'Video slots');
    const header = element('div', 'evs-caption');
    header.append(element('span', '', 'Clips'), element('span', '', 'Drag rows to reorder'));
    const list = element('div', 'evs-list'); list.setAttribute('aria-label', 'Video clips');
    list.tabIndex = -1;
    const releaseScroll = captureScrollableWheelInVue(list, { captureAtEdges: true });
    const footer = element('div', 'evs-add'), count = element('span');
    const add = button('+ Video', 'Add video slot', () => {
        actions.add(); list.lastElementChild?.scrollIntoView({ block: 'nearest' });
    });
    footer.append(add, count);
    const total = element('div', 'en-panel-note');
    root.append(header, list, footer, element('div', 'en-panel-note', 'Choose a file in each slot. Empty slots are ignored.'), total);
    const views = new Map();
    const rowFor = id => actions.rows().find(row => row.id === id);
    const opened = id => (actions.state().openClips ?? [actions.state().activeId]).includes(id);
    function duration(row, info) {
        const [n, d = 1] = String(info?.fps ?? '').split('/').map(Number), rate = n / d;
        if (!Number.isFinite(info?.duration) || !Number.isFinite(rate) || rate <= 0) return null;
        return Math.max(0, Math.min(info.duration - row.start_frame / rate, row.load_cap ? row.load_cap / rate : Infinity));
    }
    function create(id) {
        const card = element('article', 'evs-slot'), top = element('div', 'evs-top'); top.draggable = true;
        const include = button('', 'Include', () => actions.update(id, { enabled: !rowFor(id).enabled }));
        include.className = 'evs-enable';
        const file = button('', 'Choose video', () => actions.choose(id)); file.className = 'evs-file';
        const filename = element('span'), arrow = element('span', '', '▾'); file.append(filename, arrow);
        const order = element('span', 'evs-order');
        const up = button('↑', 'Move clip up', () => actions.move(id, -1));
        const down = button('↓', 'Move clip down', () => actions.move(id, 1)); order.append(up, down);
        const disclosure = button('', 'Clip settings', () => {
            const state = actions.state(), open = new Set(state.openClips ?? [state.activeId]);
            if (open.has(id)) open.delete(id); else open.add(id);
            actions.present({ openClips: [...open] }); actions.select(id);
        }); disclosure.className = 'evs-disclosure';
        const remove = button('×', 'Remove clip', () => actions.remove(id)); remove.className = 'evs-remove';
        top.append(include, file, order, disclosure, remove);
        const summary = button('', 'Preview clip', () => actions.select(id)); summary.className = 'evs-summary';
        const fields = element('div', 'evs-fields'), trim = element('div', 'evs-trim'), inputs = {};
        for (const [key, title] of [['start_frame', 'Start frame'], ['load_cap', 'Load cap']]) {
            const label = element('label', '', title), input = element('input'); inputs[key] = input;
            input.type = 'number'; input.min = '0'; input.max = String(2 ** 31 - 1); input.step = '1';
            input.title = key === 'start_frame' ? 'Zero-based original frame. Seeks the selected source preview.' : 'Source frames to keep. 0 = all remaining frames.';
            input.oninput = () => {
                if (input.value !== '' && input.checkValidity() && Number.isInteger(input.valueAsNumber)) {
                    actions.update(id, { [key]: input.valueAsNumber });
                }
            };
            input.onchange = () => { input.value = rowFor(id)?.[key] ?? 0; };
            label.append(input); trim.append(label);
        }
        const blend = element('div', 'evs-trim');
        if (actions.effects?.blend_modes) {
            const label = element('label', '', 'Blend to next'), select = inputs.blend_mode = element('select');
            select.setAttribute('aria-label', 'Blend to next');
            for (const value of ['inherit', ...actions.effects.blend_modes]) {
                const option = element('option', '', value === 'inherit' ? 'Use global blend' : value.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase()));
                option.value = value; option.title = actions.effects.blend_tooltips?.[value] ?? ''; select.append(option);
            }
            select.onchange = () => actions.update(id, { blend_mode: select.value }); label.append(select);
            const seconds = element('label', '', 'Blend seconds'), input = inputs.blend_duration = element('input');
            input.type = 'number'; input.min = '0'; input.max = '60'; input.step = '0.1'; input.setAttribute('aria-label', 'Blend seconds');
            input.title = 'Centered on the cut into the next enabled clip. Short clips limit the fade. The last clip has no outgoing blend.';
            input.oninput = () => { if (input.value !== '' && input.checkValidity()) actions.update(id, { blend_duration: input.valueAsNumber }); };
            input.onchange = () => { input.value = rowFor(id)?.blend_duration ?? 1; }; seconds.append(input); blend.append(label, seconds);
        }
        const toggles = element('div', 'evs-options'), bar = element('div', 'en-panel-bar'), flags = {};
        for (const [key, title] of [['mute', 'Mute'], ['use_metadata', 'Use metadata']]) {
            const toggle = button(title, title, () => actions.update(id, { [key]: !rowFor(id)[key] }));
            flags[key] = toggle; bar.append(toggle);
        }
        const duplicate = button('⧉', 'Duplicate clip', () => actions.duplicate(id)); duplicate.className = 'evs-duplicate';
        toggles.append(bar, duplicate);
        const details = element('div', 'evs-detail'); fields.append(trim, blend, toggles, details); card.append(top, summary, fields);
        card.onclick = event => { if (!event.target.closest('button,input,select,label')) actions.select(id); };
        card.onkeydown = event => {
            if (event.altKey && ['ArrowUp', 'ArrowDown'].includes(event.key)) {
                event.preventDefault(); actions.move(id, event.key === 'ArrowUp' ? -1 : 1);
            }
        };
        top.ondragstart = event => { event.dataTransfer.setData('text/eclipse-video', id); event.stopPropagation(); };
        top.ondragend = () => { for (const view of views.values()) view.card.classList.remove('evs-drop'); };
        card.ondragover = event => { if (event.dataTransfer.types.includes('text/eclipse-video')) { event.preventDefault(); card.classList.add('evs-drop'); } };
        card.ondragleave = () => card.classList.remove('evs-drop');
        card.ondrop = event => {
            const source = event.dataTransfer.getData('text/eclipse-video');
            if (source) { event.preventDefault(); event.stopPropagation(); card.classList.remove('evs-drop'); actions.reorder(source, id); }
        };
        return { card, include, file, filename, up, down, disclosure, remove, summary, fields, inputs, flags, duplicate, details };
    }
    function render() {
        const rows = actions.rows(), ids = new Set(rows.map(row => row.id));
        for (const [id, view] of views) if (!ids.has(id)) { view.card.remove(); views.delete(id); }
        for (const [index, row] of rows.entries()) {
            let view = views.get(row.id);
            if (!view) { view = create(row.id); views.set(row.id, view); }
            // Retain focused fields and media while a numeric edit updates state.
            if (list.children[index] !== view.card) list.insertBefore(view.card, list.children[index] ?? null);
            const info = row.file ? actions.probe(row.file) : null, seconds = duration(row, info), open = Boolean(row.file) && opened(row.id);
            view.card.setAttribute('aria-label', `Video slot ${index + 1}`);
            view.card.setAttribute('aria-current', String(row.id === actions.state().activeId));
            view.card.classList.toggle('evs-disabled', !row.enabled);
            view.include.textContent = row.enabled ? '✓' : '×'; view.include.setAttribute('aria-pressed', String(row.enabled));
            view.file.setAttribute('aria-label', `Choose video for slot ${index + 1}`);
            view.filename.textContent = row.file?.filename || 'Choose video…'; view.file.classList.toggle('evs-empty', !row.file);
            view.file.title = row.file ? `${row.file.type}/${row.file.subfolder}/${row.file.filename}` : 'Browse or upload a video for this slot';
            view.disclosure.textContent = open ? '▾' : '▸'; view.disclosure.setAttribute('aria-expanded', String(open)); view.disclosure.disabled = !row.file;
            view.up.disabled = index === 0; view.down.disabled = index === rows.length - 1; view.duplicate.disabled = rows.length >= 128;
            view.summary.hidden = open;
            view.summary.textContent = row.file ? `Start ${row.start_frame} · cap ${row.load_cap || 'all'}${seconds == null ? '' : ` · ${seconds.toFixed(2)}s`}${row.mute ? ' · muted' : ''}${row.use_metadata ? ' · GenData' : ''}${info?.error ? ' · unavailable' : ''}` : 'Empty · choose a file to set its trim';
            view.fields.hidden = !open;
            for (const [key, input] of Object.entries(view.inputs)) {
                if (key === 'start_frame' || key === 'load_cap') input.setAttribute('aria-label', key === 'start_frame' ? 'Start frame' : 'Load cap');
                if (document.activeElement !== input) input.value = String(row[key] ?? (key === 'blend_mode' ? 'inherit' : key === 'blend_duration' ? 1 : 0));
            }
            if (view.inputs.blend_mode) {
                view.inputs.blend_mode.title = actions.effects.blend_tooltips?.[row.blend_mode] ?? 'Transition into the next enabled clip. Use global blend inherits its mode and duration.';
                view.inputs.blend_duration.disabled = ['inherit', 'cut'].includes(row.blend_mode ?? 'inherit');
            }
            for (const [key, toggle] of Object.entries(view.flags)) {
                toggle.setAttribute('aria-pressed', String(row[key])); toggle.disabled = key === 'use_metadata' && !row.enabled;
            }
            view.details.textContent = info?.error ? 'File unavailable — choose a file to replace it.' : info?.width
                ? `${info.fps} FPS · ${info.duration.toFixed(2)}s source${seconds == null ? '' : ` · ${seconds.toFixed(2)}s selected`}` : 'Reading source details…';
        }
        count.textContent = `${rows.length} / 128 slots`; add.disabled = rows.length >= 128;
        const included = rows.filter(row => row.enabled && row.file), lengths = included.map(row => duration(row, actions.probe(row.file)));
        total.textContent = `${included.length} clips included${included.length && lengths.every(n => n != null) ? ` · ${lengths.reduce((a, b) => a + b, 0).toFixed(2)}s selected` : ''}`;
    }
    return { element: root, footer, render, destroy: releaseScroll };
}
