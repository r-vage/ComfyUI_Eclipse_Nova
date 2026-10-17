/** Active resize settings and preserved drafts for conditionally rendered controls. */
export const NODE_ID = 'Image Resize [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_RESIZE_CONFIGURATION';
export const EDITOR_KEY = 'eclipseResizeV2';
const clone = value => JSON.parse(JSON.stringify(value));

export function activeFields(config) {
    const fields = ['scale_to', 'fit', 'method', 'divisible_by', 'device', 'use_input_size'];
    fields.push(...(config.scale_to === 'custom' ? ['custom_width', 'custom_height'] : ['size', 'aspect_ratio']));
    if (!['resize', 'stretch'].includes(config.fit)) fields.push('crop_position');
    if (config.fit === 'pad') fields.push('pad_color');
    return fields;
}

export class ResizeState {
    constructor(raw, spec, editor = {}) {
        const config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        if (!config || config.version !== 1 || !Object.hasOwn(spec.choices.scale_to, config.scale_to)
            || !Object.hasOwn(spec.choices.fit, config.fit)) throw Error('Expected version 1 resize configuration.');
        if (!Object.hasOwn(config, 'use_input_size')) config.use_input_size = true;
        if (typeof config.use_input_size !== 'boolean') throw Error('Use inputs must be enabled or disabled.');
        const fields = ['version', ...activeFields(config)];
        if (Object.keys(config).some(key => !fields.includes(key)) || fields.some(key => !Object.hasOwn(config, key))) {
            throw Error('Resize configuration has missing or unsupported fields.');
        }
        this.config = config; this.spec = spec; this.editor = clone(editor);
    }
    value() { return JSON.stringify(this.config); }
    change(key, value) {
        const previous = this.config, values = { ...this.spec.defaults, ...this.editor.drafts, ...previous, [key]: value };
        const fields = activeFields(values); this.editor.drafts ??= {};
        for (const name of activeFields(previous)) if (!fields.includes(name)) this.editor.drafts[name] = previous[name];
        this.config = { version: 1, ...Object.fromEntries(fields.map(name => [name, values[name]])) };
        for (const name of fields) delete this.editor.drafts[name];
    }
}
