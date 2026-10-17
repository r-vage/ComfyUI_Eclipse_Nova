/** Named image-source values, section state and inactive resize drafts. */
export const IMAGE_ID = 'Load Image [Eclipse Nova]';
export const FILES_ID = 'Load Files From Folder [Eclipse Nova]';
export const IMAGE_WIDGET = 'ECLIPSE_NOVA_LOAD_IMAGE';
export const FILES_WIDGET = 'ECLIPSE_NOVA_LOAD_FILES';
export const EDITOR_KEY = 'eclipseImageLoader';
export const clone = value => JSON.parse(JSON.stringify(value));
export const METADATA_GROUPS = { sampler: ['sampler_name', 'scheduler', 'steps', 'cfg'], positive: ['text_pos'], negative: ['text_neg'], seed: ['seed'] };
export class LoaderState {
    constructor(raw, spec, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        this.spec = spec; this.editor = clone(editor);
        if (spec.kind === 'image' && this.config && !Object.hasOwn(this.config, 'metadata_fields')) this.config.metadata_fields = Object.fromEntries(Object.keys(METADATA_GROUPS).map(key => [key, true]));
        const keys = spec.kind === 'image' ? ['version', 'source', 'files', 'metadata', 'metadata_fields']
            : ['version', 'paths', 'mode', 'recursive', 'metadata', 'stop_at_end', 'revision', 'sort', 'single', 'range', 'step', 'resize'];
        if (!this.config || this.config.version !== 1 || Object.keys(this.config).length !== keys.length
            || keys.some(key => !Object.hasOwn(this.config, key))) throw Error('Expected version 1 image loader configuration.');
        if (spec.kind === 'image') {
            const fields = this.config.metadata_fields;
            if (!fields || Object.keys(fields).length !== Object.keys(METADATA_GROUPS).length
                || Object.keys(METADATA_GROUPS).some(key => typeof fields[key] !== 'boolean')) throw Error('Invalid metadata selection.');
        }
    }
    value() { return JSON.stringify(this.config); }
    toggleResize() {
        if (this.config.resize) { this.editor.resizeDraft = this.config.resize; this.config.resize = null; }
        else { this.config.resize = clone(this.editor.resizeDraft ?? this.spec.resize_default); this.openSection('resize'); }
    }
    sectionOpen(key) { return this.editor.sections?.[key] ?? ['selection', 'generation'].includes(key); }
    openSection(key) {
        this.editor.sections ??= {};
        for (const name of ['selection', 'sorting', 'resize']) if (!this.editor.pins?.[name]) this.editor.sections[name] = false;
        this.editor.sections[key] = true;
    }
    toggleSection(key) { if (this.sectionOpen(key)) (this.editor.sections ??= {})[key] = false; else this.openSection(key); }
    togglePin(key) { const pins = this.editor.pins ??= {}; pins[key] = !pins[key]; if (pins[key]) (this.editor.sections ??= {})[key] = true; }
}
