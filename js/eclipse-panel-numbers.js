/** Optional sliders for the existing numeric inputs in Eclipse Nova panels. */
let useSliders = false;
const panels = new Set();

export function setUseSliders(enabled) {
    useSliders = enabled === true;
    for (const panel of panels) { panel.sync(); panel.measure(); }
}

export class PanelNumbers {
    constructor(root, measure) {
        this.root = root; this.measure = measure; this.controls = new Map();
        this.onInput = () => this.sync();
        root.addEventListener('input', this.onInput);
        root.addEventListener('change', this.onInput);
        panels.add(this);
    }
    sync() {
        const inputs = new Set(useSliders ? this.root.querySelectorAll('input[type="number"]') : []);
        for (const [input, control] of this.controls) {
            if (!inputs.has(input)) { this.remove(input, control); this.controls.delete(input); }
        }
        for (const input of inputs) {
            // Unbounded inputs and seed text controls must keep their exact-entry UI.
            const bounded = input.min !== '' && input.max !== '' && Number.isFinite(Number(input.min))
                && Number.isFinite(Number(input.max)) && Number(input.max) > Number(input.min);
            if (!bounded) {
                if (this.controls.has(input)) this.remove(input, this.controls.get(input));
                this.controls.delete(input); continue;
            }
            let control = this.controls.get(input);
            if (!control) {
                const wrapper = document.createElement('span'); wrapper.className = 'en-panel-number-control';
                const slider = document.createElement('input'); slider.type = 'range';
                const label = input.closest('label'), originalFor = label?.getAttribute('for'), originalId = input.id;
                const title = input.getAttribute('aria-label') || label?.querySelector('span')?.textContent
                    || input.dataset.field || 'Value';
                slider.setAttribute('aria-label', `${title} slider`);
                if (label) { input.id ||= `en-number-${crypto.randomUUID()}`; label.htmlFor = input.id; }
                input.before(wrapper); wrapper.append(input, slider);
                slider.oninput = () => {
                    if (slider.disabled) return;
                    input.value = slider.value;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                };
                slider.onchange = () => {
                    if (!slider.disabled) input.dispatchEvent(new Event('change', { bubbles: true }));
                };
                control = { wrapper, slider, label, originalFor, originalId };
                this.controls.set(input, control);
            }
            const { slider } = control;
            for (const key of ['min', 'max', 'step']) if (slider[key] !== input[key]) slider[key] = input[key];
            slider.disabled = input.disabled || input.readOnly;
            // The slider has its own browser clamping. Never write that value
            // back just because a number is empty, invalid, or off its step.
            slider.value = input.value;
        }
    }
    remove(input, { wrapper, slider, label, originalFor, originalId }) {
        slider.oninput = slider.onchange = null;
        wrapper.replaceWith(input);
        if (label) {
            if (originalFor === null) label.removeAttribute('for'); else label.htmlFor = originalFor;
            input.id = originalId;
        }
    }
    dispose() {
        panels.delete(this);
        this.root.removeEventListener('input', this.onInput);
        this.root.removeEventListener('change', this.onInput);
        for (const [input, control] of this.controls) this.remove(input, control);
        this.controls.clear();
    }
}
