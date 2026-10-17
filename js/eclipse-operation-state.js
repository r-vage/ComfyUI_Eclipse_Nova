/** SPDX-License-Identifier: Apache-2.0
 * Named settings for fixed-input operations; section state stays in the workflow.
 */
export const WIDGET_TYPE = 'ECLIPSE_NOVA_OPERATION';
export const EDITOR_KEY = 'eclipseOperationV2';
const clone = value => JSON.parse(JSON.stringify(value));
const hasFields = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));

export class OperationState {
    constructor(raw, spec, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        this.spec = clone(spec); this.editor = clone(editor);
        const c = this.config;
        if (!hasFields(c, ['version', 'kind', 'parameters']) || c.version !== 1 || c.kind !== spec.kind
            || !hasFields(c.parameters, Object.keys(spec.fields))
            || Object.entries(spec.fields).some(([key, field]) => {
                const value = c.parameters[key];
                if (field.type === 'BOOLEAN') return typeof value !== 'boolean';
                if (['INT', 'FLOAT'].includes(field.type)) return value !== null && typeof value !== 'number';
                return typeof value !== 'string';
            })) throw Error(`Expected version 1 ${spec.title} configuration.`);
    }
    value() { return JSON.stringify(this.config); }
    sectionOpen(key) { return this.editor.sections?.[key] ?? key === this.spec.layout.sections?.[0]?.key; }
    toggleSection(key) {
        const open = !this.sectionOpen(key); this.editor.sections ??= {};
        if (open) for (const other of [...(this.spec.layout.sections ?? []).map(s => s.key), 'result']) {
            if (!this.editor.pins?.[other]) this.editor.sections[other] = false;
        }
        this.editor.sections[key] = open;
    }
    togglePin(key) {
        const pins = this.editor.pins ??= {}; pins[key] = !pins[key];
        if (pins[key]) (this.editor.sections ??= {})[key] = true;
    }
}
