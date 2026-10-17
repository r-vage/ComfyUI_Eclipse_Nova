/** Execution options and per-node section state for the structured saver. */
export const NODE_ID = 'Save Images [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_SAVE_IMAGES';
export const EDITOR_KEY = 'eclipseSaveImages';
export const SECTIONS = { output: 'Output', format: 'Format', metadata: 'Metadata' };
const clone = value => JSON.parse(JSON.stringify(value));

export class SaveImagesState {
    constructor(raw, spec, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        // Workflow properties may be Vue proxies after loading or undo.
        this.spec = spec; this.editor = clone(editor);
        const config = this.config, fields = spec.fields;
        if (!config || config.version !== 1 || Object.keys(config).length !== 2 || !config.options
            || Array.isArray(config.options) || Object.keys(config.options).length !== fields.length
            || fields.some(field => {
                const value = config.options[field.key];
                return typeof value !== typeof field.default
                    || (typeof value === 'number' && (!Number.isInteger(value) || value < field.min || value > field.max))
                    || (typeof value === 'string' && (value.includes('\0') || value.length > (field.maxLength ?? 4096)))
                    || (field.options && !field.options.includes(value));
            })) throw Error('Invalid Save Images configuration.');
    }
    value() { return JSON.stringify(this.config); }
    sectionOpen(key) { return this.editor.sections?.[key] === true; }
    toggleSection(key) {
        const open = !this.sectionOpen(key); this.editor.sections ??= {};
        if (open) for (const other of Object.keys(SECTIONS)) if (!this.editor.pins?.[other]) this.editor.sections[other] = false;
        this.editor.sections[key] = open;
    }
    togglePin(key) {
        this.editor.pins ??= {}; this.editor.pins[key] = !this.editor.pins[key];
        if (this.editor.pins[key]) { this.editor.sections ??= {}; this.editor.sections[key] = true; }
    }
    visible(field) {
        const options = this.config.options, saving = options.save_to_disk;
        if (!saving && field.section === 'metadata' && field.key !== 'embed_workflow') return false;
        const format = saving ? options.extension : 'png';
        if (field.formats && !field.formats.includes(format)) return false;
        if (field.key === 'output_path') return options.use_output;
        if (field.key.startsWith('filename_')) return options.use_filename;
        if (field.key === 'quality') return options.use_quality;
        if (field.key === 'dpi') return options.use_dpi;
        if (['remove_prompts', 'add_loras_to_prompt'].includes(field.key)) return options.save_generation_data;
        return true;
    }
    summary(key) {
        const o = this.config.options;
        if (key === 'output') return o.use_output ? o.output_path || 'ComfyUI output' : 'ComfyUI output';
        if (key === 'format') return [o.extension.toUpperCase(), o.extension === 'webp' && o.lossless_webp ? 'Lossless' : ''].filter(Boolean).join(' · ');
        return this.spec.fields.filter(field => field.section === 'metadata' && this.visible(field) && o[field.key]).map(field => field.label).join(' · ') || 'None';
    }
}
