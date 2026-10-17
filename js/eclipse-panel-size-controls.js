/** Aspect, resolution, custom size and divisor controls shared by dimension panels. */
import { element } from './eclipse-panel-controls.js';
import { dimensionAspect, sizeError } from './eclipse-panel-sizing.js';
import { SizeMenu } from './eclipse-panel-size-menu.js';

export class SizeControls {
    constructor(controller, parent) { this.controller = controller; this.sizes = new SizeMenu(); this.build(parent); }
    get state() { return this.controller.state; }
    get config() { return this.state.config; }
    edit(fn, render = true) { this.controller.edit(fn, render); }
    input(parent, name, key, value, setter, field = {}) {
        const label = element('label', 'en-panel-field'), input = element('input'); input.type = field.type ?? 'text';
        input.value = value ?? ''; input.dataset.field = key; input.required = true;
        for (const name of ['min', 'max', 'step', 'pattern', 'maxLength', 'inputMode']) if (field[name] != null) input[name] = field[name];
        if (field.title) input.title = field.title;
        input.oninput = () => this.edit(() => setter(input.type === 'number' ? input.value === '' ? null : Number(input.value) : input.value), false);
        label.append(element('span', '', name), input); parent.append(label); return input;
    }
    build(parent) {
        const size = this.config.size, sizing = size.sizing, spec = this.state.spec.sizing;
        const drafts = this.state.sizingDrafts();
        const grid = element('div', 'en-panel-grid'); parent.append(grid);
        const choose = (name, key, current, choices, change, extra = {}) => this.sizes.field(grid, {
            name, key: `size.${key}`, value: current, choices, change: selected => this.edit(state => change(state, selected)), ...extra,
        });
        const aspects = [{ value: 'custom', label: 'Custom', group: 'General' }, ...Object.entries(spec.aspects).map(([name, ratio]) => ({
            value: name, label: name, ratio, group: ratio[0] === ratio[1] ? 'Square' : ratio[0] > ratio[1] ? 'Horizontal' : 'Vertical',
        }))];
        const ratio = dimensionAspect(size), fixed = sizing.mode === 'fixed';
        const aspect = choose('Aspect', 'aspect', sizing.aspect, aspects, (state, aspect) => state.changeSize({ aspect }),
            { disabled: fixed, ...(fixed ? { display: { label: ratio.join(':'), ratio } } : {}) });
        if (fixed) aspect.trigger.title = 'Aspect follows the fixed width and height.';
        choose('Resolution', 'resolution', sizing.mode === 'preset' ? sizing.resolution : 'custom', [
            { value: 'custom', label: 'Custom', group: 'General' },
            ...Object.entries(spec.resolutions).map(([key, value]) => ({ value: key, ...value })),
        ], (state, resolution) => state.changeSize(resolution === 'custom' ? { mode: drafts.customMode ?? 'megapixels' } : { mode: 'preset', resolution }));
        const customDivisor = drafts.customDivisor || !spec.divisors.includes(sizing.divisor);
        choose('Divisible by', 'divisor', customDivisor ? 'custom' : sizing.divisor,
            [...spec.divisors.map(value => ({ value, label: String(value) })), { value: 'custom', label: 'Custom' }], (state, value) => {
                const saved = state.sizingDrafts(); saved.customDivisor = value === 'custom';
                if (value !== 'custom') state.changeSize({ divisor: value });
            });
        if (customDivisor) this.input(grid, 'Custom divisor', 'size.customDivisor', sizing.divisor, value => this.state.changeSize({ divisor: value }), { ...spec.divisor, type: 'number' });
        if (sizing.mode !== 'preset') {
            const mode = choose('Custom size', 'customMode', sizing.mode, [
                { value: 'megapixels', label: 'Megapixels' }, { value: 'fixed', label: 'Fixed pixels' },
            ], (state, mode) => {
                state.sizingDrafts().customMode = mode; state.changeSize({ mode });
            });
            mode.trigger.parentElement.classList.add('en-size-wide');
        }
        const fixedInputs = {};
        if (fixed) for (const key of ['width', 'height']) {
            const field = this.state.spec.dimensions[key];
            const input = this.input(grid, field.label, `size.${key}`, size[key], value => this.state.changeSize({}, { [key]: value }), { ...field, type: 'number', step: sizing.divisor });
            input.onchange = () => { input.value = size[key] ?? ''; this.sync(); }; fixedInputs[key] = input;
        }
        else {
            if (sizing.aspect === 'custom') for (const [key, label] of [['ratioWidth', 'Ratio W'], ['ratioHeight', 'Ratio H']]) {
                this.input(grid, label, `size.${key}`, sizing[key], value => this.state.changeSize({ [key]: value }), { ...spec.ratio, type: 'number' });
            }
            if (sizing.mode === 'megapixels') this.input(grid, 'Megapixels', 'size.megapixels', sizing.megapixels, value => this.state.changeSize({ megapixels: value }), { ...spec.megapixels, type: 'number' });
        }
        const readout = element('div', 'en-panel-note'); readout.setAttribute('role', 'status'); parent.append(readout);
        this.syncSize = () => {
            const error = sizeError(size, this.state.spec); readout.classList.toggle('en-panel-error', !!error);
            readout.textContent = error || `${size.width} × ${size.height} · ${(size.width * size.height / 1_000_000).toFixed(2)} MP`;
            if (fixed) {
                const ratio = dimensionAspect(size); aspect.display(ratio.join(':'), ratio);
                for (const [key, input] of Object.entries(fixedInputs)) {
                    if (Number.isInteger(size.sizing.divisor) && size.sizing.divisor > 0) { input.step = size.sizing.divisor; input.min = Math.ceil(16 / size.sizing.divisor) * size.sizing.divisor; }
                    if (document.activeElement !== input) input.value = size[key] ?? '';
                }
            }
        };
        this.syncSize();
    }
    sync() { this.syncSize?.(); }
    dispose() { this.sizes.close(); }
}
