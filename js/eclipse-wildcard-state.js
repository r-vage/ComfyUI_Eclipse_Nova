/** Wildcard text/list state shared by both canvas renderers. */
import { SeedState } from './eclipse-panel-seed.js';

export const NODE_ID = 'Wildcard Processor [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_WILDCARD_LIST';
export const EDITOR_KEY = 'eclipseWildcardList';
const clone = value => JSON.parse(JSON.stringify(value));
const sections = ['prompt', 'result', 'seed'];

export class WildcardState extends SeedState {
    constructor(raw, spec, editor = {}) {
        super(); this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        this.spec = spec; this.editor = clone(editor);
        const c = this.config, keys = ['version', 'mode', 'texts', 'seed'];
        if (!c || c.version !== 1 || Object.keys(c).length !== keys.length || Object.keys(c).some(key => !keys.includes(key))
            || !['populate', 'fixed'].includes(c.mode) || !c.texts || Object.keys(c.texts).length !== 2
            || ['prompt', 'result'].some(key => typeof c.texts[key] !== 'string')
            || !c.seed || Object.keys(c.seed).length !== 3 || typeof c.seed.value !== 'string'
            || !['local', 'input'].includes(c.seed.source) || !['fixed', 'random', 'increment', 'decrement'].includes(c.seed.policy)) {
            throw Error('Invalid wildcard configuration.');
        }
    }
    value() { return JSON.stringify(this.config); }
    result() { return this.config.mode === 'fixed' ? this.config.texts.result : this.editor.preview?.text ?? ''; }
    setMode(mode) {
        if (!['populate', 'fixed'].includes(mode) || mode === this.config.mode) return;
        if (mode === 'fixed' && typeof this.editor.preview?.text === 'string') this.config.texts.result = this.editor.preview.text;
        this.config.mode = mode;
        this.editor.sections ??= {}; this.editor.sections.result = true;
    }
    sectionOpen(key) { return this.editor.sections?.[key] ?? key !== 'seed'; }
    toggleSection(key) {
        const open = !this.sectionOpen(key); this.editor.sections ??= {};
        if (open) for (const other of sections) if (!this.editor.pins?.[other]) this.editor.sections[other] = false;
        this.editor.sections[key] = open;
    }
    togglePin(key) {
        this.editor.pins ??= {}; this.editor.pins[key] = !this.editor.pins[key];
        if (this.editor.pins[key]) { this.editor.sections ??= {}; this.editor.sections[key] = true; }
    }
    setLocalSeed(enabled, connected) {
        if (!enabled && !connected) return;
        this.config.seed.source = enabled ? 'local' : 'input';
    }
    insertWildcard(token, start, end) {
        const text = this.config.texts.prompt;
        const a = Math.max(0, Math.min(text.length, start)), b = Math.max(a, Math.min(text.length, end));
        const next = text.slice(0, a) + token + text.slice(b);
        if (next.length > this.spec.maxText) throw Error('The wildcard would exceed the prompt length limit.');
        this.config.texts.prompt = next;
        return a + token.length;
    }
}
