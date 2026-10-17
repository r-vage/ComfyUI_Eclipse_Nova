/** SPDX-License-Identifier: Apache-2.0
 * Shot Planner settings and editor-only section state.
 */
import { SeedState } from './eclipse-panel-seed.js';

export const NODE_ID = 'Character Shot Planner [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_SHOT_PLANNER';
export const EDITOR_KEY = 'eclipseShotPlannerV2';
const clone = value => JSON.parse(JSON.stringify(value));
const fieldsMatch = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));

export class ShotPlannerState extends SeedState {
    constructor(raw, spec, editor = {}) {
        super(); this.config = typeof raw === 'string' ? JSON.parse(raw) : clone(raw);
        this.spec = spec; this.editor = clone(editor);
        const c = this.config;
        if (!fieldsMatch(c, ['version', 'mode', 'parameters', 'texts', 'seed']) || c.version !== 1
            || !['Planner', 'Manual'].includes(c.mode)
            || !fieldsMatch(c.parameters, [...Object.keys(spec.numbers), ...Object.keys(spec.choices), 'project', 'batch_id', 'expression', 'operation'])
            || !fieldsMatch(c.texts, Object.keys(spec.texts)) || Object.values(c.texts).some(value => typeof value !== 'string')
            || !fieldsMatch(c.seed, ['source', 'value', 'policy']) || !['local', 'input'].includes(c.seed.source)
            || typeof c.seed.value !== 'string' || !['fixed', 'random', 'increment', 'decrement'].includes(c.seed.policy)) {
            throw Error('Expected version 1 Shot Planner configuration.');
        }
    }
    value() { return JSON.stringify(this.config); }
    sectionOpen(key) { return this.editor.sections?.[key] ?? key === 'batch'; }
    toggleSection(key) {
        const open = !this.sectionOpen(key); this.editor.sections ??= {};
        if (open) for (const other of ['batch', 'character_lock', 'outfit_lock', 'scene', 'manual_shots', 'planning', 'history', 'seed']) {
            if (!this.editor.pins?.[other]) this.editor.sections[other] = false;
        }
        this.editor.sections[key] = open;
    }
    togglePin(key) {
        const pins = this.editor.pins ??= {}; pins[key] = !pins[key];
        if (pins[key]) (this.editor.sections ??= {})[key] = true;
    }
    setLocalSeed(enabled, connected) {
        if (!enabled && !connected) return;
        this.config.seed.source = enabled ? 'local' : 'input';
    }
}
