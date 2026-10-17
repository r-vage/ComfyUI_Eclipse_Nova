/** SPDX-License-Identifier: Apache-2.0
 * Named configuration fields stay independent of visible sections and stages.
 */
export const WIDGET_TYPE = 'ECLIPSE_NOVA_CHARACTER';
export const EDITOR_KEY = 'eclipseCharacterV2';
export const NODE_IDS = [
    'Character Reference Prepare [Eclipse Nova]', 'Character Reference Pack [Eclipse Nova]',
    'Character Sheet Pack [Eclipse Nova]', 'Character Sheet Split [Eclipse Nova]',
];
const clone = value => JSON.parse(JSON.stringify(value));
const fieldsMatch = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));

export class CharacterState {
    constructor(raw, spec, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw); this.spec = spec; this.editor = clone(editor);
        const c = this.config;
        if (!fieldsMatch(c, ['version', 'kind', 'parameters']) || c.version !== 1 || c.kind !== spec.kind
            || !fieldsMatch(c.parameters, spec.keys)
            || Object.keys(spec.texts).some(key => typeof c.parameters[key] !== 'string')
            || Object.keys(spec.choices).some(key => typeof c.parameters[key] !== 'string')
            || Object.keys(spec.toggles).some(key => typeof c.parameters[key] !== 'boolean')) {
            throw Error(`Expected version 1 ${spec.title} configuration.`);
        }
    }
    value() { return JSON.stringify(this.config); }
    sectionOpen(key) { return this.editor.sections?.[key] ?? key === ({ prepare: 'description', reference_pack: 'canvas', sheet_pack: 'canvas', sheet_split: 'crop' }[this.config.kind]); }
    toggleSection(key) {
        const open = !this.sectionOpen(key); this.editor.sections ??= {};
        if (open) for (const other of ['canvas', 'mannequin', 'description', 'instructions', 'identity', 'body_description', 'outfit', 'scene', 'extra_rules', 'details', 'crop', 'report']) {
            if (!this.editor.pins?.[other]) this.editor.sections[other] = false;
        }
        this.editor.sections[key] = open;
    }
    togglePin(key) {
        const pins = this.editor.pins ??= {}; pins[key] = !pins[key];
        if (pins[key]) (this.editor.sections ??= {})[key] = true;
    }
}
