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
        this.editor.detailEnabled = this.effectEnabled('detail');
    }
    value() { return JSON.stringify(this.config); }
    defaults(key) { return Object.fromEntries(Object.entries(this.spec.groups[key]).map(([name, field]) => [name, field.default])); }
    effectEnabled(key) {
        if (key !== 'detail') return this.config[key] !== null;
        // Older workflows have no section switch. Their active settings remain
        // authoritative, including when restored over stale editor properties.
        return this.editor.detailEnabled === true || this.config.processing.detail_enhance
            || Object.entries(this.config.detail).some(([name, value]) => value !== this.spec.groups.detail[name].default);
    }
    toggleEffect(key) {
        if (key === 'detail') {
            const drafts = this.editor.drafts ??= {};
            if (this.effectEnabled(key)) {
                drafts.detail = { settings: clone(this.config.detail), enhance: this.config.processing.detail_enhance };
                // Keep the existing backend contract: disabled detail serializes
                // neutral values, while the workflow retains the editor draft.
                this.config.detail = this.defaults(key); this.config.processing.detail_enhance = false;
                this.editor.detailEnabled = false;
            } else {
                this.config.detail = clone(drafts.detail?.settings ?? this.defaults(key));
                this.config.processing.detail_enhance = drafts.detail?.enhance ?? false;
                this.editor.detailEnabled = true; delete drafts.detail; this.openSection(key);
            }
            return;
        }
        if (!this.spec.optional.includes(key)) return;
        const drafts = this.editor.drafts ??= {};
        if (this.config[key] !== null) { drafts[key] = clone(this.config[key]); this.config[key] = null; }
        else {
            this.config[key] = clone(drafts[key] ?? this.defaults(key)); delete drafts[key]; this.openSection(key);
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
