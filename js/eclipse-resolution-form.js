/** Compact Jade resolution editor with a single optional Batch size mode. */
import { element, button } from './eclipse-panel-controls.js';
import { SizeControls } from './eclipse-panel-size-controls.js';

export class ResolutionForm {
    constructor(controller) { this.controller = controller; }
    render() {
        this.dispose();
        const { root, state } = this.controller;
        const focused = root.contains(document.activeElement) ? document.activeElement.dataset.field : null;
        const content = element('div', 'en-panel-content'), bar = element('div', 'en-panel-bar');
        const collapsed = state.editor.collapsed === true;
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Mode');
        const disclosure = button('', 'Mode', () => this.controller.edit(state => { state.editor.collapsed = !collapsed; }));
        disclosure.className = 'en-panel-disclosure'; disclosure.dataset.field = 'mode'; disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Mode:'));
        if (collapsed) disclosure.append(element('span', 'en-panel-summary', state.hasBatch() ? 'Batch size' : 'Size only'));
        bar.append(disclosure);
        if (!collapsed) {
            const batch = button('Batch size', 'Batch size', () => this.controller.edit(state => state.toggleBatch()));
            batch.dataset.field = 'mode.batch_size'; batch.setAttribute('aria-pressed', String(state.hasBatch()));
            batch.title = 'Include batch_size in the output pipe.'; bar.append(batch);
        }
        content.append(bar);
        this.sizeControls = new SizeControls(this.controller, content);
        if (state.hasBatch()) {
            const label = element('label', 'en-panel-inline'), input = element('input');
            input.type = 'number'; input.required = true; input.dataset.field = 'batch_size';
            for (const key of ['min', 'max', 'step']) input[key] = state.spec.batch_size[key];
            input.value = state.config.batch_size ?? '';
            input.oninput = () => this.controller.edit(state => { state.config.batch_size = input.value === '' ? null : Number(input.value); }, false);
            label.append(element('span', '', 'Batch size'), input); content.append(label);
        }
        root.replaceChildren(content);
        if (focused) [...root.querySelectorAll('[data-field]')].find(item => item.dataset.field === focused)?.focus({ preventScroll: true });
        this.controller.measure();
    }
    syncSummaries() { this.sizeControls?.sync(); }
    dispose() { this.sizeControls?.dispose(); }
}
