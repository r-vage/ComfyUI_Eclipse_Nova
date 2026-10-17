/** Stable paths, explicit ordering and inactive drafts for Smart Prompt. */
import { SeedState } from './eclipse-panel-seed.js';
export const NODE_ID = 'Smart Prompt [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_SMART_PROMPT';
export const EDITOR_KEY = 'eclipseSmartPrompt';
export const clone = value => JSON.parse(JSON.stringify(value));
const unique = values => [...new Set(values)];
const ordered = (saved, present) => {
    const available = new Set(present);
    return unique([...(saved ?? []).filter(id => available.has(id)), ...present]);
};
const own = (record, key) => record && Object.hasOwn(record, key) ? record[key] : undefined;

export class PromptState extends SeedState {
    constructor(raw, editor = {}) {
        super(); this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw); this.editor = clone(editor);
        const c = this.config;
        if (c?.version !== 1 || !Array.isArray(c.folders) || !c.seed || !['local', 'input'].includes(c.seed.source)
            || Object.keys(c).some(key => !['version', 'folders', 'seed'].includes(key))
            || c.folders.some(f => typeof f.id !== 'string' || !Array.isArray(f.files))) throw Error('Invalid Smart Prompt configuration.');
    }
    value() { return JSON.stringify(this.config); }
    folder(id) { return this.config.folders.find(folder => folder.id === id); }
    folderOrder(catalog) {
        return ordered(this.editor.order, [...this.config.folders.map(f => f.id), ...Object.keys(this.editor.drafts ?? {}), ...catalog.folders.map(f => f.id)]);
    }
    fileOrder(id, catalog) {
        const folder = catalog.folders.find(f => f.id === id);
        return ordered(own(this.editor.fileOrder, id), [...(folder?.files.map(f => f.id) ?? []), ...this.selections(id).map(f => f.id)]);
    }
    selections(id) { return this.folder(id)?.files ?? own(this.editor.drafts, id) ?? []; }
    selection(folder, file) { return this.selections(folder).find(row => row.id === file) ?? { id: file, mode: 'none' }; }
    setSelection(folder, file, selection, catalog) {
        const active = this.folder(folder); if (!active) return;
        active.files = active.files.filter(row => row.id !== file);
        if (selection.mode !== 'none') active.files.push({ ...selection, id: file });
        this.sortFiles(folder, this.fileOrder(folder, catalog));
    }
    sortFiles(id, order) { this.folder(id)?.files.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id)); }
    toggleFolder(id, catalog) {
        this.editor.order = this.folderOrder(catalog);
        const active = this.folder(id);
        if (active) { this.editor.drafts = { ...this.editor.drafts, [id]: clone(active.files) }; this.config.folders = this.config.folders.filter(f => f.id !== id); }
        else {
            this.config.folders.push({ id, files: clone(own(this.editor.drafts, id) ?? []) });
            this.config.folders.sort((a, b) => this.editor.order.indexOf(a.id) - this.editor.order.indexOf(b.id));
            this.openSection(`folder:${id}`);
        }
    }
    moveFolder(id, delta, catalog) {
        const order = this.folderOrder(catalog), active = order.filter(key => this.folder(key)), index = active.indexOf(id), other = active[index + delta];
        if (!other) return;
        const from = order.indexOf(id), to = order.indexOf(other); [order[from], order[to]] = [order[to], order[from]];
        this.editor.order = order;
        this.config.folders.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
    }
    moveFile(folder, id, delta, catalog) {
        const order = this.fileOrder(folder, catalog), index = order.indexOf(id), to = index + delta;
        if (index < 0 || to < 0 || to >= order.length) return;
        order.splice(index, 1); order.splice(to, 0, id);
        this.editor.fileOrder = { ...this.editor.fileOrder, [folder]: order }; this.sortFiles(folder, order);
    }
    reset(folder = null) { for (const item of this.config.folders) if (folder === null || item.id === folder) item.files = []; }
    sectionOpen(key) { return this.editor.sections?.[key] === true; }
    openSection(key) {
        this.editor.sections ??= {};
        for (const other of Object.keys(this.editor.sections)) if (!this.editor.pins?.[other]) this.editor.sections[other] = false;
        this.editor.sections[key] = true;
    }
    toggleSection(key) {
        if (!this.sectionOpen(key)) this.openSection(key);
        else this.editor.sections[key] = false;
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
