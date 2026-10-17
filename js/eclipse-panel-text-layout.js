/** Persist native text-field resize handles without watching canvas geometry. */
const MIN_TEXT_HEIGHT = 64;
const savedHeight = value => Number.isFinite(value) && value >= MIN_TEXT_HEIGHT ? value : MIN_TEXT_HEIGHT + 1;

export class TextFieldSizes {
    constructor(controller, { bounded = false } = {}) {
        this.controller = controller;
        this.bounded = bounded; this.fields = new Map();
        if (bounded) controller.root.classList.add('en-panel-text-bounded');
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
        content.dataset.textCount = String(this.fields.size);
        const grows = [...this.fields.values()].map(field => savedHeight(this.controller.state.editor.textHeights?.[field]) - MIN_TEXT_HEIGHT);
        const hasSpace = grows.some(grow => grow > 0);
        for (const [input, field] of this.fields) {
            const section = input.closest('[data-text-section]');
            // Pixel heights are preferences for the split, never minimum node sizes.
            section.style.setProperty('--en-text-grow', hasSpace ? savedHeight(this.controller.state.editor.textHeights?.[field]) - MIN_TEXT_HEIGHT : 1);
        }
    }
    resize(input, requested) {
        input.style.height = '';
        const inputs = [...this.fields.keys()].filter(field => field.isConnected);
        if (inputs.length < 2 || !inputs.includes(input)) return;
        const heights = inputs.map(field => field.offsetHeight);
        const total = heights.reduce((sum, height) => sum + height, 0), spare = total - MIN_TEXT_HEIGHT * inputs.length;
        if (spare <= 0) return;
        const target = inputs.indexOf(input), wanted = Math.max(MIN_TEXT_HEIGHT, Math.min(requested, MIN_TEXT_HEIGHT + spare));
        const remaining = total - wanted - MIN_TEXT_HEIGHT * (inputs.length - 1);
        const others = heights.reduce((sum, height, i) => sum + (i === target ? 0 : Math.max(0, height - MIN_TEXT_HEIGHT)), 0);
        const next = Object.fromEntries(inputs.map((field, i) => [this.fields.get(field), i === target ? wanted
            : MIN_TEXT_HEIGHT + remaining * (others ? Math.max(0, heights[i] - MIN_TEXT_HEIGHT) / others : 1 / (inputs.length - 1))]));
        this.controller.edit(state => { state.editor.textHeights = { ...state.editor.textHeights, ...next }; }, false);
        this.layout(input.closest('.en-panel-text-layout'));
    }
    disconnect() { this.observer.disconnect(); this.fields.clear(); }
}
