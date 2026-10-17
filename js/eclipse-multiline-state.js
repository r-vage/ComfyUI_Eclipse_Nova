/** Text and filtering state; wrapping and disclosure are workflow presentation only. */
export const NODE_ID = 'String Multiline [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_MULTILINE';
export const EDITOR_KEY = 'eclipseMultiline';

export class MultilineState {
    constructor(raw, spec, editor = {}) {
        const config = typeof raw === 'string' ? JSON.parse(raw) : structuredClone(raw);
        if (!config || Array.isArray(config) || Object.keys(config).some(key => !['version', 'text', 'filter', 'preview', 'stop'].includes(key))
            || config.version !== 1 || typeof config.text !== 'string'
            || ['filter', 'preview', 'stop'].some(key => key in config && typeof config[key] !== 'boolean')
            || config.text.length > spec.maxTextLength) throw Error('Invalid multiline configuration.');
        this.config = config; this.spec = spec;
        // Workflow properties can be Vue proxies after undo or renderer changes.
        this.editor = { ...JSON.parse(JSON.stringify(editor)), wrap: editor.wrap !== false, collapsed: editor.collapsed === true };
    }
    setText(text) {
        if (typeof text !== 'string' || text.length > this.spec.maxTextLength) throw Error('Text exceeds the editor limit.');
        this.config.text = text;
    }
    result(connected) {
        if (!connected) return this.config.filter ? '' : this.config.text;
        return this.editor.preview?.text ?? '';
    }
    value() { return JSON.stringify(this.config); }
}
