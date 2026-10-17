/** Named styles and queue-time index actions for the compact Prompt Styler. */
export const NODE_ID = 'Prompt Styler [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_PROMPT_STYLER';
export const EDITOR_KEY = 'eclipsePromptStyler';
export const MODES = { tag_based: 'Tags', natural_language: 'Natural language', custom: 'Custom' };
export const FLAGS = { apply_to_positive: 'Positive', apply_to_negative: 'Negative', spaces_to_underscores: 'Underscores', log_prompt: 'Log' };
export const clone = value => JSON.parse(JSON.stringify(value));
const shortcuts = { '-1': 'random', '-2': 'increment', '-3': 'decrement' };
export const selectionKey = config => JSON.stringify([config.style_mode, config.style, config.index, config.policy]);
const wrap = (value, count) => (value % count + count) % count;

export class StylerState {
    constructor(raw, spec, editor = {}) {
        const config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        const keys = ['version', 'style_mode', 'style', 'index', 'policy', ...Object.keys(FLAGS), 'max_words_to_combine'];
        if (!config || Array.isArray(config) || config.version !== 1 || Object.keys(config).length !== keys.length
            || keys.some(key => !Object.hasOwn(config, key)) || !Object.hasOwn(MODES, config.style_mode)
            || typeof config.style !== 'string' || !config.style.trim()
            || !Number.isInteger(config.index) || config.index < 0 || config.index > 999999
            || !['fixed', ...Object.values(shortcuts)].includes(config.policy)
            || Object.keys(FLAGS).some(key => typeof config[key] !== 'boolean')
            || !Number.isInteger(config.max_words_to_combine) || config.max_words_to_combine < 2 || config.max_words_to_combine > 10) {
            throw Error('Invalid Prompt Styler configuration.');
        }
        this.config = config; this.spec = spec; this.editor = clone(editor);
    }
    value() { return JSON.stringify(this.config); }
    indexInput(names = []) {
        const index = Number.isInteger(this.config.index) && names.includes(this.config.style) ? names.indexOf(this.config.style) : this.config.index;
        return Object.keys(shortcuts).find(key => shortcuts[key] === this.config.policy) ?? String(index ?? '');
    }
    selectStyle(style, names) {
        this.config.style = style; this.config.index = Math.max(0, names.indexOf(style));
    }
    setIndex(raw, names) {
        if (Object.hasOwn(shortcuts, raw)) { this.config.policy = shortcuts[raw]; return; }
        this.config.policy = 'fixed';
        const index = /^\d+$/.test(raw) ? Number(raw) : NaN;
        if (!Number.isInteger(index) || index > 999999) { this.config.index = null; return; }
        this.config.index = names.length ? index % names.length : index;
        if (names.length) this.config.style = names[this.config.index];
    }
    step(delta, names) {
        if (!names.length) return;
        const current = names.indexOf(this.config.style);
        this.config.policy = 'fixed'; this.selectStyle(names[wrap(Math.max(0, current) + delta, names.length)], names);
    }
    changeMode(mode, names) {
        this.editor.selections = { ...this.editor.selections, [this.config.style_mode]: this.config.style };
        this.config.style_mode = mode;
        const previous = this.editor.selections[mode];
        this.selectStyle(previous ?? (names.includes(this.config.style) ? this.config.style : names[0] ?? 'base'), names);
    }
    useLast(names) {
        const last = this.editor.lastStyle; if (!last) return;
        this.config.style_mode = last.mode; this.config.policy = 'fixed';
        this.selectStyle(last.style, names);
    }
}

export function resolveSelection(config, names, last, random = Math.random) {
    if (!names.length) throw Error('No styles available. Refresh the style list.');
    let index = names.indexOf(config.style);
    if (config.policy === 'random') {
        const choices = names.filter(name => names.length === 1 || last?.mode !== config.style_mode || name !== last.style);
        index = names.indexOf(choices[Math.min(choices.length - 1, Math.floor(random() * choices.length))]);
    } else if (index < 0) throw Error(`Style '${config.style}' is unavailable. Refresh and select a style.`);
    return { mode: config.style_mode, style: names[index], index };
}

export function acceptSelection(state, before, selected, names) {
    if (selectionKey(state.config) === selectionKey(before)) {
        const step = before.policy === 'increment' ? 1 : before.policy === 'decrement' ? -1 : 0;
        const index = wrap(selected.index + step, names.length);
        state.config.style = names[index]; state.config.index = index;
    }
    state.editor.lastStyle = clone(selected);
}
