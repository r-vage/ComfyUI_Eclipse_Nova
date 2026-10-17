/** Eclipse Nova image adjustments: serialized active stages and editor drafts. */
export const NODE_ID = 'Image Filter Adjustments Advanced [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_IMAGE_ADJUSTMENTS';
export const EDITOR_KEY = 'eclipseImageAdjustments';
export const TITLES = { soften: 'Soften', scale: 'Scale', color_match: 'Color match', color: 'Color & light',
    detail: 'Detail & blur', grade: 'LUT & solarize', sharpen: 'Smart sharpen', finish: 'Lens & grain' };
const clone = value => JSON.parse(JSON.stringify(value));
const fieldsMatch = (value, keys) => value && !Array.isArray(value) && typeof value === 'object'
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));

export class AdjustmentsState {
    constructor(raw, spec, editor = {}) {
        const config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        if (!fieldsMatch(config, ['version', 'processing', ...Object.keys(spec.groups)]) || config.version !== 1
            || !fieldsMatch(config.processing, Object.keys(spec.processing))
            || Object.values(config.processing).some(value => typeof value !== 'boolean')
            || Object.entries(spec.groups).some(([key, fields]) => !(spec.optional.includes(key) && config[key] === null)
                && !fieldsMatch(config[key], Object.keys(fields)))) throw Error('Expected version 1 image adjustments configuration.');
        this.spec = spec; this.config = config; this.editor = clone(editor);
    }
    value() { return JSON.stringify(this.config); }
    toggleEffect(key) {
        if (!this.spec.optional.includes(key)) return;
        const drafts = this.editor.drafts ??= {};
        if (this.config[key] !== null) { drafts[key] = clone(this.config[key]); this.config[key] = null; }
        else {
            const defaults = Object.fromEntries(Object.entries(this.spec.groups[key]).map(([name, field]) => [name, field.default]));
            this.config[key] = clone(drafts[key] ?? defaults); delete drafts[key]; this.openSection(key);
        }
    }
    sectionOpen(key) { return this.editor.sections?.[key] === true; }
    openSection(key) {
        this.editor.sections ??= {};
        for (const other of Object.keys(TITLES)) if (other !== key && !this.editor.pins?.[other]) this.editor.sections[other] = false;
        this.editor.sections[key] = true;
    }
    toggleSection(key) { if (this.sectionOpen(key)) this.editor.sections[key] = false; else this.openSection(key); }
    togglePin(key) {
        const pins = this.editor.pins ??= {}; pins[key] = !pins[key];
        if (pins[key]) (this.editor.sections ??= {})[key] = true;
    }
}
