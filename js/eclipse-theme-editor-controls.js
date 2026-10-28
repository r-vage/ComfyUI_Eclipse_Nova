/** Color and shadow controls for the Eclipse Nova theme editor. */
import { element, button } from './eclipse-panel-controls.js';

export function parseColor(value) {
    if (value === 'transparent') return { rgb: '#000000', alpha: 0 };
    if (!/^#(?:[\da-f]{3,4}|[\da-f]{6}|[\da-f]{8})$/i.test(value)) return null;
    let hex = value.slice(1);
    if (hex.length < 5) hex = [...hex].map(c => c + c).join('');
    return { rgb: `#${hex.slice(0, 6)}`, alpha: hex.length === 8 ? parseInt(hex.slice(6), 16) / 255 : 1 };
}

export function fieldLabel(parent, title, input) {
    const label = element('label', 'en-theme-field'); label.append(element('span', '', title), input);
    input.setAttribute('aria-label', title); parent.append(label); return input;
}

export function colorControl(parent, title, value, change, opaque = false, transparent = true) {
    const row = element('div', 'en-theme-color');
    const picker = element('input'); picker.type = 'color'; picker.setAttribute('aria-label', `${title} color`);
    const hex = element('input'); hex.type = 'text'; hex.spellcheck = false; hex.required = true;
    hex.setAttribute('aria-label', `${title} value`); hex.value = value;
    const alpha = element('input'); alpha.type = 'number'; alpha.min = '0'; alpha.max = '100'; alpha.step = '0.01';
    alpha.setAttribute('aria-label', `${title} opacity`); alpha.title = 'Opacity (%)'; alpha.required = true;
    const percent = element('span', '', '%');
    const sync = () => {
        const color = parseColor(hex.value);
        const valid = color && (!opaque || /^#[\da-f]{6}$/i.test(hex.value)) && (transparent || hex.value !== 'transparent');
        hex.setCustomValidity(valid ? '' : opaque ? 'Use a six-digit hex color.' : `Use a hex color with optional alpha${transparent ? ', or transparent' : ''}.`);
        if (!valid) return false;
        picker.value = color.rgb; alpha.value = String(Math.round(color.alpha * 10000) / 100);
        return true;
    };
    hex.oninput = () => { if (sync()) change(hex.value); };
    const update = () => {
        if (!alpha.checkValidity()) return;
        const a = Math.round(Number(alpha.value) * 255 / 100);
        hex.value = picker.value + (!opaque && a < 255 ? a.toString(16).padStart(2, '0') : '');
        hex.setCustomValidity(''); change(hex.value);
    };
    picker.oninput = update; alpha.oninput = update;
    row.append(picker, hex); if (!opaque) row.append(alpha, percent);
    const wrap = element('div', 'en-theme-field'); wrap.append(element('span', '', title), row); parent.append(wrap);
    sync(); return wrap;
}

export function parseShadow(value) {
    if (value === 'none') return [];
    return value.split(',').map(layer => {
        const [x, y, blur, color] = layer.trim().split(/\s+/);
        return { x: parseFloat(x), y: parseFloat(y), blur: parseFloat(blur), color };
    });
}
export function formatShadow(layers) {
    const length = value => Number(value) ? `${Number(value)}px` : '0';
    return layers.map(({ x, y, blur, color }) => `${length(x)} ${length(y)} ${length(blur)} ${color}`).join(', ') || 'none';
}

export function shadowControl(parent, title, value, change) {
    let layers = parseShadow(value);
    const wrap = element('fieldset', 'en-theme-shadow'); wrap.append(element('legend', '', title));
    const rows = element('div'), raw = element('code', 'en-theme-shadow-value', value);
    const commit = () => { raw.textContent = formatShadow(layers); change(raw.textContent); };
    const add = button('Add shadow', `Add ${title.toLowerCase()} layer`, () => {
        layers.push({ x: 0, y: 0, blur: 10, color: '#00000080' }); render(); commit();
    });
    const render = () => {
        rows.replaceChildren(); add.disabled = layers.length >= 4;
        layers.forEach((layer, index) => {
            const row = element('div', 'en-theme-shadow-layer'), positions = element('div', 'en-theme-shadow-position');
            for (const [key, label] of [['x', 'X'], ['y', 'Y'], ['blur', 'Blur']]) {
                const input = element('input'); input.type = 'number'; input.min = '0'; input.max = '999.99'; input.step = '0.01';
                input.value = String(layer[key]); input.required = true;
                fieldLabel(positions, `${title} ${index + 1} ${label}`, input);
                input.oninput = () => { if (input.checkValidity()) { layer[key] = Number(input.value); commit(); } };
            }
            positions.append(button('Remove', `Remove ${title.toLowerCase()} layer ${index + 1}`, () => {
                layers.splice(index, 1); render(); commit();
            }));
            row.append(positions);
            colorControl(row, `${title} ${index + 1}`, layer.color, color => { layer.color = color; commit(); }, false, false);
            rows.append(row);
        });
    };
    wrap.append(raw, rows, add); parent.append(wrap); render();
}
