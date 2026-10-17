/** Structured FX settings, inactive effect drafts and section presentation. */
export const NODE_IDS = ['Image with FX [Eclipse Nova]', 'Text Image with FX [Eclipse Nova]'];
export const WIDGET_TYPE = 'ECLIPSE_NOVA_FX_CONFIGURATION';
export const EDITOR_KEY = 'eclipseFxV2';
export const EFFECTS = { stroke: 'Stroke', glow: 'Glow', shadow: 'Shadow' };
const clone = value => JSON.parse(JSON.stringify(value));
const fieldsMatch = (value, keys) => value && !Array.isArray(value) && typeof value === 'object'
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));

export class FxState {
    constructor(raw, spec, editor = {}) {
        const config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        this.spec = spec;
        const effects = this.effects();
        if (!fieldsMatch(config, ['version', 'kind', 'parameters', ...effects]) || config.version !== 1
            || config.kind !== spec.kind || !fieldsMatch(config.parameters, spec.groups[spec.kind])
            || effects.some(key => config[key] !== null && !fieldsMatch(config[key], spec.groups[key]))) {
            throw Error(`Expected version 1 ${spec.kind} FX configuration.`);
        }
        this.config = config; this.editor = clone(editor);
    }
    value() { return JSON.stringify(this.config); }
    effects() { return this.spec.kind === 'text' ? ['stroke', 'glow', 'shadow'] : ['glow', 'shadow']; }
    sections() { return [this.spec.kind, ...(this.spec.kind === 'text' ? ['layout'] : []), 'placement', ...this.effects()]; }
    toggleEffect(key) {
        if (!this.effects().includes(key)) return;
        const drafts = this.editor.drafts ??= {};
        if (this.config[key] !== null) { drafts[key] = this.config[key]; this.config[key] = null; }
        else {
            this.config[key] = clone(drafts[key] ?? this.spec.defaults[key]); delete drafts[key];
            this.openSection(key);
        }
    }
    sectionOpen(key) { return this.editor.sections?.[key] ?? key === this.spec.kind; }
    openSection(key) {
        this.editor.sections ??= {};
        for (const other of this.sections()) if (other !== key && !this.editor.pins?.[other]) this.editor.sections[other] = false;
        this.editor.sections[key] = true;
    }
    toggleSection(key) { if (!this.sectionOpen(key)) this.openSection(key); else (this.editor.sections ??= {})[key] = false; }
    togglePin(key) {
        const pins = this.editor.pins ??= {}; pins[key] = !pins[key];
        if (pins[key]) (this.editor.sections ??= {})[key] = true;
    }
}
