/** Canonical Smart Folder settings, inactive drafts and disclosure state. */
import { SeedState, MAX_SEED, validSeed, randomSeed } from './eclipse-panel-seed.js';
import { changeSize } from './eclipse-panel-sizing.js';
export const NODE_ID = 'Smart Folder [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_FOLDER_CONFIGURATION';
export const EDITOR_KEY = 'eclipseSmartFolderV2';
export const clone = value => JSON.parse(JSON.stringify(value));
export const FEATURES = [['date_time', 'Date/time'], ['batch', 'Batch folder'], ['size', 'Size'],
    ['vhs', 'VHS'], ['loop', 'Loop'], ['context_length', 'Context'], ['duration', 'Duration'], ['seed', 'Seed']];
const VIDEO_FEATURES = new Set(['vhs', 'loop', 'context_length', 'duration']);
const SECTIONS = ['folder', 'size', 'video', 'vhs', 'context', 'seed'];

export function parseConfiguration(raw) {
    const config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
    if (config?.version !== 1 || !['image', 'video'].includes(config.mode) || !config.folder || typeof config.folder !== 'object'
        || Array.isArray(config.folder) || Object.keys(config).some(key => !['version', 'mode', 'folder', 'batch_size', 'size', 'video', 'seed'].includes(key))
        || (config.mode === 'video' && (!config.video || typeof config.video !== 'object'))
        || (config.mode === 'image' && config.video) || (config.size && !config.size.sizing)) {
        throw Error('Expected version 1 Smart Folder configuration.');
    }
    if (config.size) delete config.size.latent_type;
    return config;
}

export class FolderState extends SeedState {
    constructor(raw, spec, editor = {}) {
        super(); this.config = parseConfiguration(raw); this.spec = spec; this.editor = clone(editor);
        for (const mode of ['image', 'video']) {
            // Inactive size drafts also belong to dimensions, not a model format.
            for (const size of [this.editor.modes?.[mode]?.size, this.editor.drafts?.[mode]?.size]) {
                if (size && typeof size === 'object') delete size.latent_type;
            }
        }
    }
    value() { return JSON.stringify(this.config); }
    features() { return FEATURES.filter(([key]) => this.config.mode === 'video' || !VIDEO_FEATURES.has(key)); }
    owner(key) { return ['date_time', 'batch'].includes(key) ? this.config.folder : VIDEO_FEATURES.has(key) ? this.config.video : this.config; }
    enabled(key) { return Object.hasOwn(this.owner(key) ?? {}, key); }
    toggle(key) {
        if (key === 'context_length' && this.enabled('loop')) return;
        const owner = this.owner(key), shared = ['date_time', 'batch', 'seed'].includes(key);
        const drafts = ((this.editor.drafts ??= {})[shared ? 'common' : this.config.mode] ??= {});
        if (this.enabled(key)) { drafts[key] = owner[key]; delete owner[key]; }
        else {
            owner[key] = clone(drafts[key] ?? this.spec.defaults[key === 'size' ? `${this.config.mode}_size` : key]);
            delete drafts[key];
            if (key === 'loop' && !this.enabled('context_length')) {
                this.config.video.context_length = drafts.context_length ?? this.spec.defaults.context_length; delete drafts.context_length;
            }
            const section = { date_time: 'folder', batch: 'folder', context_length: 'context', loop: 'context', duration: 'video' }[key] ?? key;
            this.openSection(section);
        }
    }
    mode(mode) {
        if (mode === this.config.mode || !['image', 'video'].includes(mode)) return;
        const { config } = this, modes = this.editor.modes ??= {};
        modes[config.mode] = { root: config.folder.root, ...(config.size ? { size: config.size } : {}), ...(config.video ? { video: config.video } : {}) };
        const target = modes[mode] ?? { root: mode === 'image' ? 'images' : 'videos', ...(mode === 'video' ? { video: clone(this.spec.defaults.video) } : {}) };
        config.mode = mode; config.folder.root = target.root;
        delete config.size; delete config.video;
        if (target.size) config.size = target.size;
        if (mode === 'video') config.video = target.video;
        delete modes[mode];
    }
    sizingDrafts() { return (this.editor.sizing ??= {})[this.config.mode] ??= {}; }
    changeSize(patch, dimensions = {}) { changeSize(this.config.size, patch, dimensions, this.sizingDrafts(), this.spec); }
    sectionOpen(key) { return this.editor.sections?.[key] ?? key === 'folder'; }
    openSection(key) {
        this.editor.sections ??= {};
        for (const other of SECTIONS) if (other !== key && !this.editor.pins?.[other]) this.editor.sections[other] = false;
        this.editor.sections[key] = true;
    }
    toggleSection(key) { if (!this.sectionOpen(key)) this.openSection(key); else (this.editor.sections ??= {})[key] = false; }
    togglePin(key) {
        const pins = this.editor.pins ??= {}; pins[key] = !pins[key];
        if (pins[key]) (this.editor.sections ??= {})[key] = true;
    }
}

export function queueConfiguration(raw, random = randomSeed) {
    const config = parseConfiguration(raw);
    if (config.seed) {
        if (!validSeed(config.seed.value) || !['fixed', 'random', 'increment', 'decrement'].includes(config.seed.policy)) throw Error('Seed must be an unsigned 64-bit decimal value or -1, -2, -3.');
        if (config.seed.policy === 'random') config.seed.value = random();
    }
    return config;
}
export const nextCounter = (value, minimum = 0n) => validSeed(value) ? String(BigInt(value) === MAX_SEED ? minimum : BigInt(value) + 1n) : value;
