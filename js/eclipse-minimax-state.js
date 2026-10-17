/** SPDX-License-Identifier: Apache-2.0
 * Named MiniMax settings and editor disclosures serialize independently.
 */
export const WIDGET_TYPE = 'ECLIPSE_NOVA_MINIMAX_H3';
export const EDITOR_KEY = 'eclipseMiniMaxH3';
export const NODE_IDS = ['Audio Timeline Planner', 'Audio Plan Step', 'Segmented Conditioning']
    .map(name => `MiniMax H3 ${name} [Eclipse Nova]`);
const clone = value => JSON.parse(JSON.stringify(value));
const fieldsMatch = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
export class MiniMaxState {
    constructor(raw, spec, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw); this.spec = spec; this.editor = clone(editor);
        const c = this.config;
        if (!fieldsMatch(c, ['version', 'kind', 'parameters']) || c.version !== 1 || c.kind !== spec.kind
            || !fieldsMatch(c.parameters, spec.keys)
            || Object.keys(spec.texts).some(key => typeof c.parameters[key] !== 'string')
            || Object.keys(spec.choices).some(key => !Object.hasOwn(spec.choices[key], c.parameters[key]))
            || Object.keys(spec.toggles).some(key => typeof c.parameters[key] !== 'boolean')) {
            throw Error(`Expected version 1 ${spec.title} configuration.`);
        }
    }
    value() { return JSON.stringify(this.config); }
    sectionOpen(key) { return this.editor.sections?.[key] ?? key === (this.config.kind.includes('step') ? 'task' : this.config.kind.includes('timeline') ? 'transitions' : 'canvas'); }
    toggleSection(key) {
        const open = !this.sectionOpen(key); this.editor.sections ??= {};
        if (open) for (const other of ['transitions', 'render', 'activity', 'technical', 'instructions', 'canvas', 'guides', 'prompt', 'task', 'report']) {
            if (!this.editor.pins?.[other]) this.editor.sections[other] = false;
        }
        this.editor.sections[key] = open;
    }
    togglePin(key) {
        const pins = this.editor.pins ??= {}; pins[key] = !pins[key];
        if (pins[key]) (this.editor.sections ??= {})[key] = true;
    }
    select(key, value) {
        const p = this.config.parameters; p[key] = value;
        if (this.config.kind === 'segmented_timeline') {
            if (p.conditioning_family === 'ref2va_active_reference') {
                p.segment_strategy = 'warmup_reset'; p.reset_anchor = 'first_only'; p.technical_split_source = 'original_image_reset';
            }
            if (p.technical_split_source === 'generated_continuation') p.technical_seam_style = 'plain_reset';
            if (p.technical_seam_style === 'intentional_camera_cut' && p.conditioning_family === 'fl2va_keyframes' && p.warmup_seconds === 0) p.warmup_seconds = 2;
        }
        if (this.config.kind === 'segmented_conditioning') {
            if (key === 'conditioning_family') {
                p.has_start_guide = value === 'fl2va_keyframes'; p.start_guide_frame_index = p.has_start_guide ? 0 : -1;
                p.has_last_image = false; p.endpoint_frame_index = -1;
            }
            if (key === 'has_start_guide') p.start_guide_frame_index = value ? Math.max(0, p.start_guide_frame_index) : -1;
            if (key === 'has_last_image') p.endpoint_frame_index = value ? Math.max(0, p.endpoint_frame_index) : -1;
        }
    }
}
