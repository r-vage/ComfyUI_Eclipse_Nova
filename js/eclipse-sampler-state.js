/** Eclipse Nova sampler state. No dependency on the legacy widget helpers. */
import { SeedState, validSeed, randomSeed } from './eclipse-panel-seed.js';
export { MAX_SEED, validSeed, randomSeed, nextSeed } from './eclipse-panel-seed.js';
export const SETTINGS_ID = 'Smart Sampler Settings [Eclipse Nova]';
export const SAMPLER_ID = 'Eclipse KSampler (Kargim) [Eclipse Nova]';
export const DETAILER_ID = 'Detailer (SEGS/pipe) [Eclipse Nova]';
export const INTEGRATED_DETAILER_ID = 'Detailer (Advanced) [Eclipse Nova]';
export const ADVANCED_ID = 'Eclipse KSampler Advanced [Eclipse Nova]';
export const NODE_IDS = new Set([SETTINGS_ID, SAMPLER_ID, DETAILER_ID, INTEGRATED_DETAILER_ID, ADVANCED_ID]);
export const WIDGET_TYPE = 'ECLIPSE_NOVA_SAMPLER_CONFIGURATION';
export const EDITOR_KEY = 'eclipseSamplerV2';
export const clone = value => JSON.parse(JSON.stringify(value));
export const FEATURES = [
    ['sampler_name', 'Sampler'], ['scheduler', 'Scheduler'], ['steps', 'Steps'], ['cfg', 'CFG'],
    ['denoise', 'Denoise'], ['guidance', 'Guidance'], ['seed', 'Seed'],
    ['noise', 'Noise injection'], ['upscale_value', 'Upscale'], ['allow_overwrite', 'Overwrite'],
];
const keysFor = key => key === 'noise' ? ['sigmas_denoise', 'noise_strength'] : [key];

export function parseConfiguration(raw) {
    const config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
    if (config?.version !== 1 || !['settings', 'sampler', 'detailer', 'detailer_auto', 'advanced'].includes(config.profile)
        || !config.parameters || Array.isArray(config.parameters) || typeof config.parameters !== 'object'
        || Object.keys(config).some(key => !['version', 'profile', 'parameters', 'seed'].includes(key))) {
        throw Error('Unsupported sampler configuration. Expected version 1.');
    }
    return config;
}

export class SamplerState extends SeedState {
    constructor(raw, spec, editor = {}) {
        super();
        this.config = parseConfiguration(raw); this.spec = spec; this.editor = clone(editor);
        if (spec.profile === 'detailer_auto' && ['auto', 'cuda'].includes(this.config.parameters.detection_device)) {
            this.config.parameters.detection_device = 'default';
        }
        if (spec.profile === 'detailer_auto' && ['BBox', 'Segm'].includes(this.config.parameters.detection_mode)) {
            const p = this.config.parameters, segm = p.detection_mode === 'Segm';
            p.yolo_model = segm ? `segm/${p.yolo_segm_model ?? 'person_yolov8m-seg.pt'}` : `bbox/${p.yolo_model ?? 'face_yolov8m.pt'}`;
            delete p.detection_mode; delete p.yolo_segm_model;
        }
        if (spec.profile === 'detailer_auto' && ['YOLO', 'SAM2', 'SEGS'].includes(this.config.parameters.detection_mode)) {
            const p = this.config.parameters, sam = p.detection_mode === 'SAM2';
            delete p.cache_model; delete p.detection_mode; p.sam2_enabled = sam;
            p.yolo_model = `bbox/${p.yolo_model ?? 'face_yolov8m.pt'}`; delete p.yolo_segm_model;
            p.refine_edges = sam && p.detail_method !== 'None'; p.detection = p.labels ?? 'all'; delete p.labels;
            p.crop_factor = p[sam ? 'sam_crop_factor' : 'yolo_crop_factor'] ?? 2.2;
            p.drop_size = p[sam ? 'sam_drop_size' : 'yolo_drop_size'] ?? 1;
            for (const key of ['sam_crop_factor', 'yolo_crop_factor', 'sam_drop_size', 'yolo_drop_size']) delete p[key];
            if (p.detail_method === 'None') p.detail_method = 'ViTMatte';
            if (!sam) Object.assign(p, { mask_grow: 0, mask_blur: 0, invert_mask: false, combined: false, bbox_fill: false, contour_fill: false });
            else p.selection = 'All';
            for (const [key, field] of Object.entries(spec.fields)) if (!Object.hasOwn(p, key)) p[key] = clone(field.default);
        }
        if (spec.profile === 'advanced' && spec.fields.second_denoise && !Object.hasOwn(this.config.parameters, 'second_denoise')) {
            this.config.parameters.second_denoise = clone(spec.fields.second_denoise.default);
        }
        for (const [key, field] of Object.entries(spec.fields)) {
            if (field.optional && !Object.hasOwn(this.config.parameters, key)) this.config.parameters[key] = clone(field.default);
        }
        if (this.config.profile !== spec.profile
            || Object.keys(this.config.parameters).some(key => !Object.hasOwn(spec.fields, key))) {
            throw Error('Configuration does not match this node.');
        }
    }
    value() { return JSON.stringify(this.config); }
    sectionOpen(key) { return this.editor.sections?.[key] ?? key === 'sampler'; }
    toggleSection(key) {
        this.editor.sections ??= {};
        const open = !this.sectionOpen(key);
        if (open) for (const other of ['detection', 'selection', 'sam', 'refinement', 'regions', 'detection_preview', 'segmentation_preview', 'sampler', 'stage2', 'upscale', 'qwen', 'dit', 'detail', 'sizing', 'mask', 'seed']) {
            if (other !== key && !this.editor.pins?.[other]) this.editor.sections[other] = false;
        }
        this.editor.sections[key] = open;
    }
    togglePin(key) {
        this.editor.pins ??= {};
        this.editor.pins[key] = !this.editor.pins[key];
        if (this.editor.pins[key]) { this.editor.sections ??= {}; this.editor.sections[key] = true; }
    }
    enabled(key) {
        if (key === 'allow_overwrite') return this.config.parameters.allow_overwrite === true;
        return key === 'seed' ? Object.hasOwn(this.config, 'seed') : Object.hasOwn(this.config.parameters, keysFor(key)[0]);
    }
    toggle(key) {
        if (key === 'allow_overwrite') {
            if (this.enabled(key)) delete this.config.parameters.allow_overwrite;
            else this.config.parameters.allow_overwrite = true;
            return;
        }
        this.editor.drafts ??= {};
        if (key === 'seed') {
            if (this.enabled(key)) { this.editor.drafts.seed = this.config.seed; delete this.config.seed; }
            else this.config.seed = this.editor.drafts.seed ?? { value: this.spec.seedDefault, policy: 'fixed' };
        } else for (const field of keysFor(key)) {
            if (Object.hasOwn(this.config.parameters, field)) {
                this.editor.drafts[field] = this.config.parameters[field]; delete this.config.parameters[field];
            } else this.config.parameters[field] = this.editor.drafts[field] ?? this.spec.fields[field].default;
        }
    }
}

export function queueConfiguration(raw, random = randomSeed) {
    const config = parseConfiguration(raw);
    if (config.seed) {
        if (!validSeed(config.seed.value) || !['fixed', 'random', 'increment', 'decrement'].includes(config.seed.policy)) {
            throw Error('Seed must be an unsigned 64-bit decimal value or -1, -2, -3.');
        }
        if (config.seed.policy === 'random') config.seed.value = random();
    }
    return config;
}
