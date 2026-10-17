/** Prompt Forge text, rating and seed state, independent of canvas rendering. */
import { SeedState } from './eclipse-panel-seed.js';

export const NODE_ID = 'Danbooru Prompt Forge [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_PROMPT_FORGE';
export const EDITOR_KEY = 'eclipsePromptForge';
const clone = value => JSON.parse(JSON.stringify(value));

export class ForgeState extends SeedState {
    constructor(raw, spec, editor = {}) {
        super(); this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        this.spec = spec; this.editor = clone(editor);
        const c = this.config, keys = ['version', 'features', 'texts', 'seed'];
        if (!c || c.version !== 1 || Object.keys(c).length !== keys.length || Object.keys(c).some(key => !keys.includes(key))
            || !Array.isArray(c.features) || c.features.some(key => !spec.features.some(feature => feature.key === key))
            || new Set(c.features).size !== c.features.length || !c.texts || Array.isArray(c.texts)
            || Object.keys(c.texts).length !== spec.texts.length || spec.texts.some(field => typeof c.texts[field.key] !== 'string')
            || !c.seed || !['local', 'input'].includes(c.seed.source) || typeof c.seed.value !== 'string'
            || !['fixed', 'random', 'increment', 'decrement'].includes(c.seed.policy)
            || Object.keys(c.seed).length !== 3) throw Error('Invalid Prompt Forge configuration.');
    }
    value() { return JSON.stringify(this.config); }
    enabled(key) { return this.config.features.includes(key); }
    toggle(key) {
        if (!this.spec.features.some(feature => feature.key === key)) return;
        if (this.enabled(key)) this.config.features = this.config.features.filter(feature => feature !== key);
        else this.config.features.push(key);
    }
    sectionOpen(key) { return this.editor.sections?.[key] ?? key === 'taglists_must_include'; }
    toggleSection(key) {
        const open = !this.sectionOpen(key); this.editor.sections ??= {};
        if (open) for (const other of [...this.spec.texts.map(field => field.key), 'result', 'seed']) {
            if (!this.editor.pins?.[other]) this.editor.sections[other] = false;
        }
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
}
