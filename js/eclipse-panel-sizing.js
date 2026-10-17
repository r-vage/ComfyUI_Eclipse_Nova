/** Aspect/area sizing adapted from Smart Model Loader; Eclipse owns this implementation. */
const numeric = (value, field) => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < field.min || value > field.max
        || (field.step === 1 && !Number.isInteger(value))) throw Error(`${field.label} must be between ${field.min} and ${field.max}.`);
    return value;
};
const gcd = (a, b) => { while (b) [a, b] = [b, a % b]; return a; };

export function dimensionAspect(size) {
    if (![size.width, size.height].every(value => Number.isInteger(value) && value > 0)) return [1, 1];
    const common = gcd(size.width, size.height); return [size.width / common, size.height / common];
}

export function resolveDimensions(size, spec) {
    const sizing = size.sizing, settings = spec.sizing;
    const divisor = numeric(sizing.divisor, settings.divisor);
    let width, height;
    if (sizing.mode === 'fixed') {
        width = numeric(size.width, spec.dimensions.width); height = numeric(size.height, spec.dimensions.height);
    } else {
        const ratio = sizing.aspect === 'custom'
            ? [numeric(sizing.ratioWidth, settings.ratio), numeric(sizing.ratioHeight, settings.ratio)] : settings.aspects[sizing.aspect];
        if (!ratio) throw Error('Select a supported aspect ratio.');
        const area = sizing.mode === 'preset' ? settings.resolutions[sizing.resolution]?.area
            : sizing.mode === 'megapixels' ? numeric(sizing.megapixels, settings.megapixels) * 1_000_000 : NaN;
        if (!Number.isFinite(area)) throw Error('Select a supported resolution.');
        width = Math.sqrt(area * ratio[0] / ratio[1]); height = Math.sqrt(area * ratio[1] / ratio[0]);
    }
    const snap = (value, field) => {
        const result = Math.max(Math.ceil(field.min / divisor), Math.floor(value / divisor + .5)) * divisor;
        if (result > field.max) throw Error('Dimensions exceed the supported size (32768 pixels per edge).');
        return result;
    };
    return { width: snap(width, spec.dimensions.width), height: snap(height, spec.dimensions.height) };
}

export function sizeError(size, spec) {
    try {
        for (const [key, field] of Object.entries(spec.dimensions)) numeric(size[key], field);
        const actual = resolveDimensions(size, spec);
        if (actual.width !== size.width || actual.height !== size.height) throw Error('Dimensions do not match the aspect, resolution or divisor.');
        return '';
    } catch (error) { return error.message; }
}

export function changeSize(size, patch, dimensions, drafts, spec) {
    const previous = size.sizing;
    let sizing = { ...previous };
    if (patch.mode && patch.mode !== previous.mode) {
        drafts[previous.mode] = structuredClone({ sizing: previous, width: size.width, height: size.height });
        const saved = drafts[patch.mode];
        let [w, h] = dimensionAspect(size);
        if (Math.max(w, h) > spec.sizing.ratio.max) { const scale = 100 / Math.max(w, h); w *= scale; h *= scale; }
        const aspect = previous.mode === 'fixed'
            ? Object.hasOwn(spec.sizing.aspects, `${w}:${h}`) ? { aspect: `${w}:${h}` } : { aspect: 'custom', ratioWidth: w, ratioHeight: h }
            : { aspect: previous.aspect, ...(previous.aspect === 'custom' ? { ratioWidth: previous.ratioWidth, ratioHeight: previous.ratioHeight } : {}) };
        sizing = saved ? structuredClone(saved.sizing) : { mode: patch.mode, ...aspect,
            ...(patch.mode === 'preset' ? { resolution: 'square-1024' } : {}),
            ...(patch.mode === 'megapixels' ? { megapixels: 1 } : {}) };
        sizing.divisor = previous.divisor;
        if (saved && patch.mode === 'fixed') Object.assign(size, { width: saved.width, height: saved.height });
    }
    Object.assign(sizing, patch);
    if (sizing.mode !== 'fixed' && sizing.aspect === 'custom') {
        const ratio = spec.sizing.aspects[previous.aspect] ?? dimensionAspect(size);
        sizing.ratioWidth ??= drafts.ratio?.[0] ?? ratio[0]; sizing.ratioHeight ??= drafts.ratio?.[1] ?? ratio[1];
        drafts.ratio = [sizing.ratioWidth, sizing.ratioHeight];
    } else { delete sizing.ratioWidth; delete sizing.ratioHeight; }
    if (sizing.mode === 'fixed') delete sizing.aspect;
    if (sizing.mode !== 'preset') delete sizing.resolution;
    if (sizing.mode !== 'megapixels') delete sizing.megapixels;
    size.sizing = sizing; Object.assign(size, dimensions);
    try { Object.assign(size, resolveDimensions(size, spec)); }
    catch { /* Preserve invalid edits so validation blocks execution instead of replacing user input. */ }
}
