/** Independent Image/Prompt controls, paired history and one shared range. */
import { SeedState, validSeed } from './eclipse-panel-seed.js';
import { StandaloneSeedState, HISTORY_LIMIT } from './eclipse-seed-state.js';
export const NODE_ID = 'Dual Seed_v2 [Eclipse Nova]';
export const WIDGET_TYPE = 'ECLIPSE_NOVA_DUAL_SEED';
export const EDITOR_KEY = 'eclipseDualSeed';
export const KEYS = ['image', 'prompt'];
export const validPair = pair => Array.isArray(pair) && pair.length === 2 && pair.every(validSeed);
export class DualSeedState {
    constructor(raw, _spec = {}, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : structuredClone(raw);
        const c = this.config;
        if (!c || Object.keys(c).sort().join() !== 'bits,seeds,version' || !c.seeds
            || Object.keys(c.seeds).sort().join() !== 'image,prompt') throw Error('Invalid Dual Seed configuration.');
        for (const key of KEYS) new StandaloneSeedState({ version: c.version, bits: c.bits, seed: c.seeds[key] });
        this.editor = { barCollapsed: editor.barCollapsed === true, resultsOpen: editor.resultsOpen === true,
            lastSeeds: Object.fromEntries(KEYS.map(key => [key, validSeed(editor.lastSeeds?.[key]) ? editor.lastSeeds[key] : undefined])),
            history: (Array.isArray(editor.history) ? editor.history : []).filter(validPair)
                .filter((pair, i, all) => all.findIndex(p => p.join() === pair.join()) === i).slice(0, HISTORY_LIMIT) };
    }
    value() { return JSON.stringify(this.config); }
    channel(key) {
        const parent = this, state = new SeedState();
        state.config = { get seed() { return parent.config.seeds[key]; }, set seed(value) { parent.config.seeds[key] = value; } };
        state.editor = { get lastSeed() { return parent.editor.lastSeeds[key]; }, set lastSeed(value) { parent.editor.lastSeeds[key] = value; } };
        Object.defineProperty(state, 'maxSeed', { get: () => (1n << BigInt(parent.config.bits)) - 1n });
        return state;
    }
    toggleBits() {
        this.config.bits = this.config.bits === 64 ? 32 : 64;
        for (const key of KEYS) if (validSeed(this.config.seeds[key].value))
            this.config.seeds[key].value = String(BigInt(this.config.seeds[key].value) & this.channel(key).maxSeed);
    }
    record(pair) {
        if (!validPair(pair)) return;
        this.editor.history = [[...pair], ...this.editor.history.filter(p => p.join() !== pair.join())].slice(0, HISTORY_LIMIT);
        KEYS.forEach((key, i) => { this.editor.lastSeeds[key] ??= pair[i]; });
    }
    reuse(pair) {
        if (!validPair(pair)) return;
        if (!pair.every(value => this.channel('image').validSeed(value))) this.config.bits = 64;
        KEYS.forEach((key, i) => this.channel(key).setSeed(pair[i]));
    }
    validSeed(pair) { return validPair(pair) && pair.every(value => this.channel('image').validSeed(value)); }
    historyLabel(pair) { return `Image: ${pair[0]} · Prompt: ${pair[1]}`; }
}
