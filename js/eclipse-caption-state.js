/** Caption settings and section presentation, independent of canvas rendering.
 * Copyright (c) 2026 r-vage. MIT License.
 */
import { SeedState } from './eclipse-panel-seed.js';

export const NODE_ID = 'Render Lyric Captions [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_LYRIC_CAPTIONS';
export const EDITOR_KEY = 'eclipseLyricCaptionsV2';
const clone = value => JSON.parse(JSON.stringify(value));
const fieldsMatch = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));

export class CaptionState extends SeedState {
    constructor(raw, spec, editor = {}) {
        super(); this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        this.spec = spec; this.editor = clone(editor);
        const c = this.config;
        if (!fieldsMatch(c, ['version', 'parameters', 'seed']) || c.version !== 1
            || !fieldsMatch(c.parameters, [...Object.keys(spec.numbers), ...Object.keys(spec.colors), ...Object.keys(spec.choices), 'font_file', 'enable_glow'])
            || !Object.hasOwn(spec.choices.mode, c.parameters.mode) || typeof c.parameters.enable_glow !== 'boolean'
            || !fieldsMatch(c.seed, ['source', 'value', 'policy']) || c.seed.source !== 'local'
            || typeof c.seed.value !== 'string' || !['fixed', 'random', 'increment', 'decrement'].includes(c.seed.policy)) {
            throw Error('Expected version 1 caption configuration.');
        }
    }
    value() { return JSON.stringify(this.config); }
    get floating() { return this.config.parameters.mode.startsWith('floating-'); }
    get animated() { return this.spec.animated.includes(this.config.parameters.mode); }
    sectionOpen(key) { return this.editor.sections?.[key] ?? key === 'canvas'; }
    toggleSection(key) {
        const open = !this.sectionOpen(key); this.editor.sections ??= {};
        if (open) for (const other of ['canvas', 'text', 'placement', 'animation', 'glow', 'alignment', 'seed']) {
            if (!this.editor.pins?.[other]) this.editor.sections[other] = false;
        }
        this.editor.sections[key] = open;
    }
    togglePin(key) {
        const pins = this.editor.pins ??= {}; pins[key] = !pins[key];
        if (pins[key]) (this.editor.sections ??= {})[key] = true;
    }
}
