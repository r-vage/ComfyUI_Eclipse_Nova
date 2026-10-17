/** Canonical dimensions and optional batch size; editor drafts never enter the PIPE. */
import { changeSize } from './eclipse-panel-sizing.js';

export const NODE_ID = 'Resolution Pipe [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_RESOLUTION_CONFIGURATION';
export const EDITOR_KEY = 'eclipseResolutionV2';
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
// ComfyUI may wrap saved properties in Vue proxies; the state is JSON data.
const clone = value => JSON.parse(JSON.stringify(value));

export class ResolutionState {
    constructor(raw, spec, editor = {}) {
        const config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        if (!object(config) || config.version !== 1 || !object(config.size) || !object(config.size.sizing)
            || Object.keys(config).some(key => !['version', 'size', 'batch_size'].includes(key))
            || Object.keys(config.size).some(key => !['width', 'height', 'sizing'].includes(key))
            || !['width', 'height'].every(key => Object.hasOwn(config.size, key))) {
            throw Error('Expected version 1 resolution configuration.');
        }
        this.config = config; this.spec = spec; this.editor = clone(editor);
    }
    value() { return JSON.stringify(this.config); }
    hasBatch() { return Object.hasOwn(this.config, 'batch_size'); }
    toggleBatch() {
        if (this.hasBatch()) { this.editor.batchSize = this.config.batch_size; delete this.config.batch_size; }
        else {
            this.config.batch_size = Object.hasOwn(this.editor, 'batchSize') ? this.editor.batchSize : this.spec.batch_size.default;
            delete this.editor.batchSize;
        }
    }
    sizingDrafts() { return this.editor.sizing ??= {}; }
    changeSize(patch, dimensions = {}) { changeSize(this.config.size, patch, dimensions, this.sizingDrafts(), this.spec); }
}
