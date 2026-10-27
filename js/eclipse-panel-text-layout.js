/** Persist native text-field resize handles without watching canvas geometry. */
const savedHeight = (value, minimum) => Number.isFinite(value) && value >= minimum ? value : minimum + 1;

export class TextFieldSizes {
    constructor(controller, { bounded = false, minHeight = 64 } = {}) {
        this.controller = controller;
        this.minHeight = minHeight;
        this.bounded = bounded; this.fields = new Map();
        if (bounded) {
            controller.root.classList.add('en-panel-text-bounded');
            controller.root.style.setProperty('--en-text-min-height', `${minHeight}px`);
        }
        this.observer = new MutationObserver(records => {
            if (controller.disposed || controller.invalid) return;
            const heights = {};
            for (const { target } of records) {
                const height = target.style.height.endsWith('px') ? parseFloat(target.style.height) : NaN;
                const field = target.dataset.field;
                if (bounded) {
                    if (Number.isFinite(height) && height > 0) this.resize(target, height);
                    continue;
                }
                if (Number.isFinite(height) && height > 0 && height !== controller.state.editor.textHeights?.[field]) heights[field] = height;
            }
            if (Object.keys(heights).length) controller.edit(state => {
                state.editor.textHeights = { ...state.editor.textHeights, ...heights };
            }, false);
        });
    }
    attach(input, field) {
        input.dataset.field = field;
        const height = this.controller.state.editor.textHeights?.[field];
        input.style.height = !this.bounded && Number.isFinite(height) && height > 0 ? `${height}px` : '';
        if (this.bounded) this.fields.set(input, field);
        this.observer.observe(input, { attributes: true, attributeFilter: ['style'] });
    }
    layout(content) {
        const minimum = this.minHeight;
        content.dataset.textCount = String(this.fields.size);
        const grows = [...this.fields.values()].map(field => savedHeight(this.controller.state.editor.textHeights?.[field], minimum) - minimum);
        const hasSpace = grows.some(grow => grow > 0);
        for (const [input, field] of this.fields) {
            const section = input.closest('[data-text-section]');
            // Pixel heights are preferences for the split, never minimum node sizes.
            section.style.setProperty('--en-text-grow', hasSpace ? savedHeight(this.controller.state.editor.textHeights?.[field], minimum) - minimum : 1);
        }
    }
    resize(input, requested) {
        const minimum = this.minHeight;
        input.style.height = '';
        const inputs = [...this.fields.keys()].filter(field => field.isConnected);
        if (inputs.length < 2 || !inputs.includes(input)) return;
        const heights = inputs.map(field => field.offsetHeight);
        const total = heights.reduce((sum, height) => sum + height, 0), spare = total - minimum * inputs.length;
        if (spare <= 0) return;
        const target = inputs.indexOf(input), wanted = Math.max(minimum, Math.min(requested, minimum + spare));
        const remaining = total - wanted - minimum * (inputs.length - 1);
        const others = heights.reduce((sum, height, i) => sum + (i === target ? 0 : Math.max(0, height - minimum)), 0);
        const next = Object.fromEntries(inputs.map((field, i) => [this.fields.get(field), i === target ? wanted
            : minimum + remaining * (others ? Math.max(0, heights[i] - minimum) / others : 1 / (inputs.length - 1))]));
        this.controller.edit(state => { state.editor.textHeights = { ...state.editor.textHeights, ...next }; }, false);
        this.layout(input.closest('.en-panel-text-layout'));
    }
    disconnect() { this.observer.disconnect(); this.fields.clear(); }
}
