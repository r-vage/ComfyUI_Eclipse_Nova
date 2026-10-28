/** Full theme-template form and a locally scoped draft preview. */
import { element, button } from './eclipse-panel-controls.js';
import { colorControl, shadowControl, fieldLabel } from './eclipse-theme-editor-controls.js';

export const titleCase = key => key.replace(/[-_]/g, ' ').replace(/^./, c => c.toUpperCase());

export function themePreview(parent) {
    const preview = element('aside', 'en-theme-preview');
    preview.append(element('h3', '', 'Preview'), element('p', 'en-theme-note', 'Draft changes appear here. Save to apply them to your nodes.'));
    const node = element('div', 'en-theme-sample');
    const heading = element('div', 'en-theme-sample-title', 'Eclipse Nova');
    const content = element('div', 'en-theme-sample-content');
    const bar = element('div', 'en-theme-sample-bar'); bar.append(element('b', '', 'Mode:'), button('Preview', 'Preview mode sample', () => {}));
    const option = button('Selected', 'Selected option sample', () => {}); option.className = 'en-theme-sample-selected'; bar.append(option);
    const text = element('textarea'); text.value = 'A place for your prompt…'; text.rows = 3; text.setAttribute('aria-label', 'Preview text field');
    const select = element('select'); select.setAttribute('aria-label', 'Preview dropdown');
    for (const label of ['A selected option', 'Another option']) select.append(element('option', '', label));
    const actions = element('div', 'en-theme-sample-actions'); actions.append(button('Action', 'Action button sample', () => {}));
    const primary = button('Primary', 'Primary button sample', () => {}); primary.className = 'en-theme-sample-primary'; actions.append(primary);
    const status = element('div', 'en-theme-sample-status');
    for (const [key, text] of [['success', 'Ready'], ['warning', 'Warning'], ['error', 'Error']]) {
        const item = element('span', '', text); item.style.color = `var(--en-${key})`; status.append(item);
    }
    content.append(bar, element('span', 'en-theme-sample-label', 'Prompt'), text, select, actions, status);
    node.append(heading, content); preview.append(node); parent.append(preview);
    return theme => {
        for (const [key, value] of Object.entries(theme.tokens)) node.style.setProperty(`--en-${key}`, value);
        node.style.setProperty('--en-node-bg', theme.node.background);
        node.style.setProperty('--en-node-title', theme.node.title);
        heading.textContent = theme.label || 'Eclipse Nova';
    };
}

export function themeForm(parent, theme, schema, change) {
    parent.replaceChildren();
    const section = (title, open = false, note = '') => {
        const details = element('details', 'en-theme-section'); details.open = open;
        details.append(element('summary', '', title));
        if (note) details.append(element('p', 'en-theme-note', note));
        const fields = element('div', 'en-theme-fields'); details.append(fields); parent.append(details); return fields;
    };
    const node = section('Node colors', true);
    for (const key of ['background', 'title']) colorControl(node, `Node ${key}`, theme.node[key], value => { theme.node[key] = value; change(); }, true);
    const groups = [
        ['Text and status', ['text', 'muted', 'label', 'error', 'success', 'warning', 'danger', 'accent']],
        ['Buttons', schema.colors.filter(key => key.startsWith('control-'))],
        ['Inputs and selectors', schema.colors.filter(key => /^(input|select)-/.test(key))],
        ['Mode bars and selection', schema.colors.filter(key => /^(bar|pill|selected)-/.test(key))],
    ];
    const assigned = new Set(groups.flatMap(([, keys]) => keys));
    groups.push(['Surfaces and menus', schema.colors.filter(key => !assigned.has(key))]);
    for (const [label, keys] of groups) {
        const fields = section(label, label === 'Buttons');
        for (const key of keys) colorControl(fields, titleCase(key), theme.tokens[key], value => { theme.tokens[key] = value; change(); });
    }
    const shadows = section('Shadows');
    for (const key of schema.shadows) shadowControl(shadows, titleCase(key), theme.tokens[key], value => { theme.tokens[key] = value; change(); });
    const layout = section('Control shape and color scheme');
    const radius = element('input'); radius.type = 'number'; radius.min = '0'; radius.max = '999.99'; radius.step = '0.01';
    radius.required = true; radius.value = String(parseFloat(theme.tokens['pill-radius']));
    fieldLabel(layout, 'Pill radius (px)', radius);
    radius.oninput = () => { if (radius.checkValidity()) { theme.tokens['pill-radius'] = Number(radius.value) ? `${Number(radius.value)}px` : '0'; change(); } };
    const scheme = element('select'); for (const name of ['dark', 'light']) { const option = element('option', '', titleCase(name)); option.value = name; scheme.append(option); }
    scheme.value = theme.tokens['color-scheme']; fieldLabel(layout, 'Color scheme', scheme);
    scheme.onchange = () => { theme.tokens['color-scheme'] = scheme.value; change(); };
    const legacy = section('Shared template colors', false,
        'These fields are kept for compatible theme files. Eclipse preserves user node colors and does not force category or routing colors.');
    colorControl(legacy, 'Routing background', theme.node.routing_background, value => { theme.node.routing_background = value; change(); }, true);
    for (const key of schema.categories) {
        const wrapper = element('div'); const enabled = element('input'); enabled.type = 'checkbox'; enabled.checked = Object.hasOwn(theme.node.category_titles, key);
        fieldLabel(wrapper, `Include ${key} title`, enabled);
        const fields = element('fieldset', 'en-theme-category'); fields.disabled = !enabled.checked;
        let color = theme.node.category_titles[key] ?? theme.node.title;
        colorControl(fields, `${titleCase(key)} title`, color, value => { color = value; theme.node.category_titles[key] = value; change(); }, true);
        enabled.onchange = () => { fields.disabled = !enabled.checked; if (enabled.checked) theme.node.category_titles[key] = color; else delete theme.node.category_titles[key]; change(); };
        wrapper.append(fields); legacy.append(wrapper);
    }
}
