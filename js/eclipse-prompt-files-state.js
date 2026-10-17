/** Prompt-file execution data; disclosure and pin state stay in node properties. */
export const READ_ID = 'Read Prompt Files [Eclipse Nova]';
export const SAVE_ID = 'Save Prompt [Eclipse Nova]';
export const READ_WIDGET = 'ECLIPSE_NOVA_READ_PROMPT_FILES';
export const SAVE_WIDGET = 'ECLIPSE_NOVA_SAVE_PROMPT';
export const EDITOR_KEY = 'eclipsePromptFiles';
const clone = value => JSON.parse(JSON.stringify(value));

export class PromptFilesState {
    constructor(raw, spec, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        this.spec = spec; this.editor = clone(editor);
        const config = this.config;
        if (!config || config.version !== 1 || Object.keys(config).length !== 2 || !config.options
            || Array.isArray(config.options) || Object.keys(config.options).length !== spec.fields.length
            || spec.fields.some(field => {
                const value = config.options[field.key];
                return typeof value !== typeof field.default
                    || (typeof value === 'number' && (!Number.isInteger(value) || value < field.min || value > field.max))
                    || (typeof value === 'string' && (value.includes('\0') || value.length > (field.maxLength ?? 4096)))
                    || (field.options && !field.options.includes(value));
            })) throw Error('Invalid prompt-file configuration.');
    }
    value() { return JSON.stringify(this.config); }
    sectionOpen(key) { return this.editor.sections?.[key] ?? key === Object.keys(this.spec.sections)[0]; }
    toggleSection(key) {
        const open = !this.sectionOpen(key); this.editor.sections ??= {};
        if (open) for (const other of Object.keys(this.spec.sections)) if (!this.editor.pins?.[other]) this.editor.sections[other] = false;
        this.editor.sections[key] = open;
    }
    togglePin(key) {
        this.editor.pins ??= {}; this.editor.pins[key] = !this.editor.pins[key];
        if (this.editor.pins[key]) { this.editor.sections ??= {}; this.editor.sections[key] = true; }
    }
    visible(field) {
        const options = this.config.options;
        if (field.formats && !field.formats.includes(options.extension)) return false;
        return !['filename_delimiter', 'filename_number_padding'].includes(field.key) || options.write_mode === 'new';
    }
    refresh() { this.config.options.revision = (this.config.options.revision + 1) % 2147483648; }
    summary(key) {
        const options = this.config.options;
        if (key === 'files') {
            const count = options.file_paths.split(/\r?\n/).filter(line => line.trim()).length;
            return `${count} file${count === 1 ? '' : 's'}`;
        }
        if (key === 'selection') {
            const last = this.editor.lastSelection;
            if (last?.stopped) return `${options.advance} · End reached`;
            const resolved = Number.isInteger(last?.index) && last.index >= 0 && last.index < last.total;
            return `${options.advance} · ${resolved ? last.index : options.index}`;
        }
        if (key === 'output') return options.output_path || (options.use_source_folder ? 'Source folder / ComfyUI output' : 'ComfyUI output');
        return `${options.extension.toUpperCase()} · ${options.write_mode.replace('_', ' ')}`;
    }
}
