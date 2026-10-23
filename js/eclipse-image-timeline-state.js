/** Manual image timeline configuration. Copyright (c) 2026 r-vage. Apache-2.0. */
export const ID = 'Load Image Timeline [Eclipse Nova]';
export const WIDGET = 'ECLIPSE_NOVA_IMAGE_TIMELINE_LOAD';
export const EDITOR = 'eclipseImageTimeline';
export const GROUPS = { sampler: ['sampler_name', 'scheduler', 'steps', 'cfg'], positive: ['text_pos'], negative: ['text_neg'], seed: ['seed'] };
export const LABELS = { sampler: 'Sampler settings', positive: 'Positive prompt', negative: 'Negative prompt', seed: 'Seed' };
const shape = (value, keys) => value && !Array.isArray(value) && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const bounded = (n, max) => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= max;
// Workflow properties may be Vue proxies, which structuredClone cannot copy.
const clone = value => JSON.parse(JSON.stringify(value));

export function newSlot(file = null) {
    return { id: crypto.randomUUID(), file, enabled: true, fit: 'crop', crop_x: 'center', crop_y: 'center',
        blend_mode: 'inherit', blend_duration: 1, use_metadata: false,
        metadata_fields: Object.fromEntries(Object.keys(GROUPS).map(key => [key, true])) };
}

export class ImageTimelineState {
    constructor(raw, spec, editor = {}) {
        const c = this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        this.spec = spec; this.editor = clone(editor);
        if (!shape(c, ['version', 'width', 'height', 'images']) || c.version !== 1
            || ['width', 'height'].some(key => !bounded(c[key], 8192) || !Number.isInteger(c[key]))
            || !Array.isArray(c.images) || c.images.length > 128) throw Error('Invalid image timeline configuration.');
        const ids = new Set(); let metadata = 0;
        for (const row of c.images) {
            if (!shape(row, ['id', 'file', 'enabled', 'fit', 'crop_x', 'crop_y', 'blend_mode', 'blend_duration', 'use_metadata', 'metadata_fields'])
                || typeof row.id !== 'string' || !row.id || row.id.length > 128 || ids.has(row.id)
                || typeof row.enabled !== 'boolean' || typeof row.use_metadata !== 'boolean'
                || !['inherit', 'pad', 'crop', 'stretch'].includes(row.fit)
                || !['left', 'center', 'right'].includes(row.crop_x) || !['top', 'center', 'bottom'].includes(row.crop_y)
                || !spec.blend_modes.includes(row.blend_mode) || !bounded(row.blend_duration, 60)
                || !shape(row.metadata_fields, Object.keys(GROUPS)) || Object.values(row.metadata_fields).some(v => typeof v !== 'boolean')) throw Error('Invalid image slot.');
            if (row.file !== null && (!shape(row.file, ['source', 'filename']) || !['input', 'output'].includes(row.file.source)
                || typeof row.file.filename !== 'string' || row.file.filename.length > 4096 || /[\\\x00]/.test(row.file.filename)
                || row.file.filename.split('/').some(part => ['', '.', '..'].includes(part)))) throw Error('Invalid image file.');
            if (row.use_metadata && (!row.enabled || !row.file || ++metadata > 1)) throw Error('Choose one enabled image as the metadata source.');
            ids.add(row.id);
        }
        if (!ids.has(this.editor.activeId)) this.editor.activeId = c.images[0]?.id ?? null;
    }
    value() { return JSON.stringify(this.config); }
    active() { return this.config.images.find(row => row.id === this.editor.activeId); }
    update(id, values) {
        const row = this.config.images.find(row => row.id === id); if (!row) return;
        Object.assign(row, values);
        if (!row.enabled || !row.file) row.use_metadata = false;
        if (row.use_metadata) for (const other of this.config.images) if (other !== row) other.use_metadata = false;
    }
    add(file = null) {
        if (this.config.images.length >= 128) return;
        const row = newSlot(file); this.config.images.push(row); this.editor.activeId = row.id;
        return row;
    }
    remove(id) {
        const index = this.config.images.findIndex(row => row.id === id); if (index < 0) return;
        this.config.images.splice(index, 1);
        if (this.editor.activeId === id) this.editor.activeId = this.config.images[Math.min(index, this.config.images.length - 1)]?.id ?? null;
    }
    move(id, target) {
        const rows = this.config.images, from = rows.findIndex(row => row.id === id), to = typeof target === 'string' ? rows.findIndex(row => row.id === target) : from + target;
        if (from < 0 || to < 0 || to >= rows.length || from === to) return;
        rows.splice(to, 0, rows.splice(from, 1)[0]);
    }
}
