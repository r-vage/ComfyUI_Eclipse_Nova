/** Per-slot video overlay controls. Copyright (c) 2026 r-vage. Apache-2.0. */
import { button, element } from './eclipse-panel-controls.js';

export const isVideoOverlay = row => row?.role === 'overlay';
export const videoOverlaySettings = (row, spec) => ({ ...spec.overlay_defaults, ...row.overlay });

export function validateVideoOverlay(row, spec, bounded) {
    if (!['sequence', 'overlay'].includes(row.role ?? 'sequence')) throw Error('Invalid video slot role.');
    if (!Object.hasOwn(row, 'overlay') && !isVideoOverlay(row)) return;
    if (!spec.overlay_defaults) throw Error('Restart ComfyUI to load video overlay support.');
    if (Object.hasOwn(row, 'overlay') && (row.overlay === null || typeof row.overlay !== 'object' || Array.isArray(row.overlay)
        || Object.keys(row.overlay).some(key => !Object.hasOwn(spec.overlay_defaults, key)))) throw Error('Invalid overlay settings.');
    const value = videoOverlaySettings(row, spec);
    if (value.target != null && (typeof value.target !== 'string' || !value.target || value.target.length > 128 || value.target === row.id)) throw Error('Invalid overlay target.');
    if (!Object.hasOwn(spec.overlay_modes, value.mode) || !bounded(value.opacity, 0, 1)
        || !bounded(value.offset, -86400, 86400) || !bounded(value.threshold, 0, 1) || !bounded(value.softness, 0, 1)) throw Error('Invalid overlay values.');
    if (value.mask != null && (typeof value.mask !== 'object' || !['input', 'output'].includes(value.mask.type)
        || typeof value.mask.filename !== 'string' || !value.mask.filename || /[/\\\0]/.test(value.mask.filename)
        || typeof value.mask.subfolder !== 'string' || /[\\\0]/.test(value.mask.subfolder)
        || (value.mask.subfolder && value.mask.subfolder.split('/').some(part => ['', '.', '..'].includes(part))))) throw Error('Invalid mask video.');
}

export function selectedVideoPreviewRows(rows, selected) {
    const baseId = isVideoOverlay(selected) ? selected.overlay?.target : selected.id;
    const base = rows.find(row => row.id === baseId && !isVideoOverlay(row) && row.file);
    if (!base || (isVideoOverlay(selected) && !base.enabled)) throw Error('Choose and enable a Sequence target before previewing this overlay.');
    return rows.filter(row => row.id === baseId || (isVideoOverlay(row) && row.overlay?.target === baseId
        && row.file && (row.enabled || row.id === selected.id)))
        .map(row => ({ ...row, enabled: true, use_metadata: false }));
}

export function createVideoOverlayControls({ id, rowFor, rows, spec, update, chooseMask, clearMask }) {
    const root = element('div', 'evs-overlay-controls');
    const roles = element('div', 'en-panel-bar'); roles.append(element('b', 'en-panel-bar-label', 'Slot:'));
    const setRole = role => {
        const row = rowFor(id), patch = { role };
        if (role === 'overlay') {
            const value = videoOverlaySettings(row, spec), items = rows(), index = items.findIndex(item => item.id === id);
            if (!value.target) value.target = items.slice(0, index).reverse().find(item => !isVideoOverlay(item) && item.enabled && item.file)?.id
                ?? items.find(item => item.id !== id && !isVideoOverlay(item) && item.enabled && item.file)?.id ?? null;
            patch.overlay = value;
        }
        update(id, patch);
    };
    const sequence = button('Sequence', 'Sequence clip', () => setRole('sequence'));
    sequence.title = 'Append this clip to the video. Its duration and audio contribute to the playlist.';
    const overlay = button('Overlay', 'Overlay clip', () => setRole('overlay'));
    overlay.title = 'Play this video over a selected Sequence clip. Uses its timing; overlay audio is ignored.';
    roles.append(sequence, overlay);
    const fields = element('div', 'evs-trim evs-overlay-fields'), inputs = {};
    const edit = patch => update(id, { overlay: { ...videoOverlaySettings(rowFor(id), spec), ...patch } });
    function select(name, label, options, title) {
        const wrapper = element('label', '', label), input = element('select'); inputs[name] = input;
        input.setAttribute('aria-label', label); input.title = title;
        for (const [value, text] of Object.entries(options)) { const option = element('option', '', text); option.value = value; input.append(option); }
        input.onchange = () => edit({ [name]: input.value || null });
        wrapper.append(input); fields.append(wrapper); return wrapper;
    }
    select('target', 'Overlay target', {}, 'Choose an enabled Sequence clip. This link follows that clip when slots move. Up to eight layers per base.');
    select('mode', 'Overlay mode', spec.overlay_modes, 'Opacity blends the whole picture. Screen adds bright details. Remove black derives a mask. Alpha needs embedded transparency. Mask video uses a separate black/white video.');
    function number(name, label, min, max, step, title) {
        const wrapper = element('label', '', label), input = element('input'); inputs[name] = input;
        input.type = 'number'; input.min = min; input.max = max; input.step = step;
        input.setAttribute('aria-label', label); input.title = title;
        input.oninput = () => { if (input.value !== '' && input.checkValidity()) edit({ [name]: input.valueAsNumber }); };
        input.onchange = () => { input.value = videoOverlaySettings(rowFor(id), spec)[name]; };
        wrapper.append(input); fields.append(wrapper); return wrapper;
    }
    number('opacity', 'Overlay opacity', 0, 1, 0.1, '0 = hidden, 1 = full strength. The base remains fully visible outside the overlay mask.');
    number('offset', 'Offset seconds', -86400, 86400, 0.1, 'Relative to the trimmed base: positive delays the overlay; negative skips its beginning. No looping or held final frame.');
    const threshold = number('threshold', 'Black threshold', 0, 1, 0.01, 'Brightness at or below this value is transparent. Higher values remove dark compression noise but can erase dark text details.');
    const softness = number('softness', 'Black softness', 0, 1, 0.01, 'Brightness range from transparent to opaque above the threshold. Zero gives a hard edge; small values soften edges.');
    const maskRow = element('div', 'evs-mask-row');
    const mask = button('Choose mask video…', 'Choose mask video', chooseMask); mask.classList.add('evs-file');
    mask.setAttribute('aria-haspopup', 'dialog');
    const maskName = element('span'); mask.replaceChildren(maskName);
    const clear = button('×', 'Clear mask video', clearMask); maskRow.append(mask, clear);
    const note = element('div', 'en-panel-note', 'Overlay audio is ignored. The target controls duration. Mask videos: white reveals, black hides; mask time zero matches the untrimmed overlay.');
    root.append(roles, fields, maskRow, note);
    function render() {
        const items = rows(), row = items.find(item => item.id === id), active = isVideoOverlay(row), value = videoOverlaySettings(row, spec);
        sequence.setAttribute('aria-pressed', String(!active)); overlay.setAttribute('aria-pressed', String(active));
        fields.hidden = note.hidden = !active;
        const choices = items.filter(item => item.id !== id && !isVideoOverlay(item) && item.enabled && item.file);
        const options = [['', 'Choose sequence clip…'], ...choices.map(item => [item.id, `${items.indexOf(item) + 1}: ${item.file.filename}`])];
        if (value.target && !choices.some(item => item.id === value.target)) options.push([value.target, 'Target unavailable — choose a sequence clip']);
        const signature = JSON.stringify(options);
        if (inputs.target.dataset.options !== signature) {
            inputs.target.replaceChildren(...options.map(([value, text]) => { const option = element('option', '', text); option.value = value; return option; }));
            inputs.target.dataset.options = signature;
        }
        for (const [name, input] of Object.entries(inputs)) if (document.activeElement !== input) input.value = value[name] ?? '';
        threshold.hidden = softness.hidden = value.mode !== 'remove_black';
        maskRow.hidden = !active || value.mode !== 'mask';
        maskName.textContent = value.mask?.filename || 'Choose mask video…'; clear.disabled = !value.mask;
        mask.title = value.mask ? `${value.mask.type}/${value.mask.subfolder}/${value.mask.filename}` : 'Choose a grayscale mask video. Its frame rate can differ from the overlay.';
    }
    function summary() {
        const row = rowFor(id), value = videoOverlaySettings(row, spec), index = rows().findIndex(item => item.id === value.target);
        return `Overlay → ${index < 0 ? 'missing target' : `slot ${index + 1}`} · ${spec.overlay_modes[value.mode]} · ${Math.round(value.opacity * 100)}%${value.offset ? ` · ${value.offset > 0 ? '+' : ''}${value.offset}s` : ''}`;
    }
    return { element: root, render, summary };
}
