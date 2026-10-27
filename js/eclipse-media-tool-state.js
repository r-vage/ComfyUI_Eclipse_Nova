/** SPDX-License-Identifier: Apache-2.0
 * Named settings and persistent presentation for the small media tool panels.
 */
export const WIDGET_TYPE = 'ECLIPSE_NOVA_MEDIA_TOOL';
export const EDITOR_KEY = 'eclipseMediaTool';
export const NODE_IDS = ['Image Convert [Eclipse Nova]', 'Image Crop by Mask [Eclipse Nova]', 'System Audio Recorder [Eclipse Nova]'];
const clone = value => JSON.parse(JSON.stringify(value));
const fieldsMatch = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));

export class MediaToolState {
    constructor(raw, spec, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw); this.spec = spec; this.editor = clone(editor);
        const fields = ['version', 'kind', 'parameters']; if (spec.kind === 'recorder') fields.push('recording_token');
        const c = this.config;
        if (c?.parameters && spec.choices?.device && ['auto', 'cuda', 'gpu', 'mps'].includes(c.parameters.device)) c.parameters.device = 'default';
        if (!fieldsMatch(c, fields) || c.version !== 1 || c.kind !== spec.kind
            || !fieldsMatch(c.parameters, Object.keys(spec.defaults))
            || Object.keys(spec.toggles).some(key => typeof c.parameters[key] !== 'boolean')
            || Object.entries(spec.defaults).some(([key, value]) => typeof value === 'string' && typeof c.parameters[key] !== 'string')
            || (spec.kind === 'recorder' && typeof c.recording_token !== 'string')) {
            throw Error(`Expected version 1 ${spec.title} configuration.`);
        }
    }
    value() { return JSON.stringify(this.config); }
    sectionOpen(key) { return this.editor.sections?.[key] ?? key === 'output'; }
    toggleSection(key) {
        const open = !this.sectionOpen(key); this.editor.sections ??= {};
        if (open) for (const other of ['output', 'framing', 'mask', 'silence']) {
            if (!this.editor.pins?.[other]) this.editor.sections[other] = false;
        }
        this.editor.sections[key] = open;
    }
    togglePin(key) {
        const pins = this.editor.pins ??= {}; pins[key] = !pins[key];
        if (pins[key]) (this.editor.sections ??= {})[key] = true;
    }
}
