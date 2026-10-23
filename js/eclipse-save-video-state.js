/** Video-save options and per-node disclosure state. */
export const NODE_ID = 'Save Video Data [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_SAVE_VIDEO';
export const EDITOR_KEY = 'eclipseSaveVideo';
export const SECTIONS = { output: 'Output', encoding: 'Encoding', trim: 'Trim & loop', metadata: 'Metadata' };
const clone = value => JSON.parse(JSON.stringify(value));

export class SaveVideoState {
    constructor(raw, spec, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        this.spec = spec; this.editor = clone(editor);
        const config = this.config;
        if (config?.options && !Array.isArray(config.options) && typeof config.options === 'object'
            && !Object.hasOwn(config.options, 'force_audio')) config.options.force_audio = false;
        if (!config || config.version !== 1 || Object.keys(config).length !== 2 || !config.options
            || Array.isArray(config.options) || Object.keys(config.options).length !== spec.fields.length
            || spec.fields.some(field => {
                const value = config.options[field.key];
                return typeof value !== typeof field.default
                    || (typeof value === 'number' && (!Number.isFinite(value) || value < field.min || value > field.max || (field.step === 1 && !Number.isInteger(value))))
                    || (typeof value === 'string' && (value.includes('\0') || value.length > (field.maxLength ?? 4096)))
                    || (field.options && !field.options.includes(value));
            })) throw Error('Invalid Save Video configuration.');
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
    canTrim(source) { return source !== 'video' && source !== 'timed'; }
    sectionVisible(key, source) { return key !== 'trim' || (this.config.options.enable_trim && this.canTrim(source)); }
    visible(field, source) {
        const o = this.config.options;
        if (field.key === 'fps') return source === 'image';
        if (field.key.startsWith('loop_')) return source === 'image' && o.trim_mode.startsWith('loop_')
            && (field.key !== 'loop_blend_frames' || o.trim_mode === 'loop_match_blend');
        if (['remove_prompts', 'add_loras_to_prompt'].includes(field.key)) return o.save_generation_data;
        return true;
    }
    summary(key, source) {
        const o = this.config.options;
        if (key === 'output') return o.filename_prefix;
        if (key === 'encoding') return `MP4 · H.264 · CRF ${o.crf}${source === 'image' ? ` · ${o.fps} fps` : ' · Source timing'}`;
        if (key === 'trim') return o.trim_mode.replaceAll('_', ' ');
        return this.spec.fields.filter(field => field.section === 'metadata' && this.visible(field, source) && o[field.key]).map(field => field.label).join(' · ') || 'None';
    }
}
