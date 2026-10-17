/** Exact seed state shared by Eclipse Nova structured panels. */
export const MAX_SEED = (1n << 64n) - 1n;
export const randomSeed = () => crypto.getRandomValues(new BigUint64Array(1))[0].toString();
export const validSeed = value => typeof value === 'string' && /^(0|[1-9][0-9]{0,19})$/.test(value) && BigInt(value) <= MAX_SEED;
const SHORTCUTS = { '-1': 'random', '-2': 'increment', '-3': 'decrement' };

export function nextSeed(seed, maximum = MAX_SEED) {
    const delta = seed.policy === 'increment' ? 1n : seed.policy === 'decrement' ? -1n : 0n;
    return { ...seed, value: String((BigInt(seed.value) + delta) & maximum) };
}

export class SeedState {
    get maxSeed() { return MAX_SEED; }
    validSeed(value) { return validSeed(value) && BigInt(value) <= this.maxSeed; }
    randomSeed() { return String(BigInt(randomSeed()) & this.maxSeed); }
    seedInput() { return Object.keys(SHORTCUTS).find(key => SHORTCUTS[key] === this.config.seed.policy) ?? this.config.seed.value; }
    setSeed(input) {
        if (!Object.hasOwn(SHORTCUTS, input)) { this.config.seed = { ...this.config.seed, value: input, policy: 'fixed' }; return; }
        const policy = SHORTCUTS[input];
        if (this.config.seed.policy === policy) return;
        let value = this.validSeed(this.config.seed.value) ? this.config.seed.value : '0';
        if (policy !== 'random' && this.validSeed(this.editor.lastSeed)) value = nextSeed({ value: this.editor.lastSeed, policy }, this.maxSeed).value;
        this.config.seed = { ...this.config.seed, value, policy };
    }
    stepSeed(delta) {
        const base = this.config.seed.policy === 'random' && this.validSeed(this.editor.lastSeed)
            ? this.editor.lastSeed : this.config.seed.value;
        if (!this.validSeed(base)) return;
        const next = BigInt(base) + BigInt(delta);
        if (next >= 0n && next <= this.maxSeed) this.config.seed = { ...this.config.seed, value: String(next), policy: 'fixed' };
    }
}
