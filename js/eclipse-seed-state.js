/** Standalone seed values are decimal strings; recent results are editor state. */
import { SeedState, validSeed } from './eclipse-panel-seed.js';

export const NODE_ID = 'Seed [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_SEED';
export const EDITOR_KEY = 'eclipseSeed';
export const HISTORY_LIMIT = 50;

export class StandaloneSeedState extends SeedState {
    constructor(raw, _spec = {}, editor = {}) {
        super(); this.config = typeof raw === 'string' ? JSON.parse(raw) : structuredClone(raw);
        const c = this.config;
        if (!c || Array.isArray(c) || Object.keys(c).length !== 3 || c.version !== 1
            || ![32, 64].includes(c.bits) || !c.seed || Object.keys(c.seed).length !== 2
            || typeof c.seed.value !== 'string' || !['fixed', 'random', 'increment', 'decrement'].includes(c.seed.policy)) {
            throw Error('Invalid Seed configuration.');
        }
        this.editor = {
            barCollapsed: editor.barCollapsed === true, resultsOpen: editor.resultsOpen === true,
            lastSeed: validSeed(editor.lastSeed) ? editor.lastSeed : undefined,
            history: [...new Set((Array.isArray(editor.history) ? editor.history : []).filter(validSeed))].slice(0, HISTORY_LIMIT),
        };
    }
    get maxSeed() { return (1n << BigInt(this.config.bits)) - 1n; }
    value() { return JSON.stringify(this.config); }
    toggleBits() {
        this.config.bits = this.config.bits === 64 ? 32 : 64;
        if (validSeed(this.config.seed.value)) this.config.seed.value = String(BigInt(this.config.seed.value) & this.maxSeed);
    }
    record(value) {
        if (!validSeed(value)) return;
        this.editor.history = [value, ...this.editor.history.filter(seed => seed !== value)].slice(0, HISTORY_LIMIT);
        this.editor.lastSeed ??= value;
    }
    reuse(value) {
        if (!validSeed(value)) return;
        if (!this.validSeed(value)) this.config.bits = 64;
        this.setSeed(value);
    }
}
