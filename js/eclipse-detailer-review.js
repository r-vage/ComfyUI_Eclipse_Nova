/** Two independent region previews, separate from the final/live sampler image. */
import { createDOMPreviewController, setDOMPreviewController } from './eclipse-dom-preview.js';
import { button, element } from './eclipse-panel-controls.js';

const previewHeight = value => Number.isFinite(value) && value >= 120 ? value : 240;

export class DetailerReview {
    constructor(controller) {
        this.controller = controller;
        this.stages = {};
        this.observer = new MutationObserver(records => {
            if (controller.disposed || controller.invalid) return;
            const heights = {};
            for (const { target } of records) {
                const stage = target.dataset.previewStage;
                const height = target.style.height.endsWith('px') ? parseFloat(target.style.height) : NaN;
                if (Number.isFinite(height) && height >= 120
                    && height !== previewHeight(controller.state.editor.previewHeights?.[stage])) heights[stage] = height;
            }
            if (Object.keys(heights).length) controller.edit(state => {
                state.editor.previewHeights = { ...state.editor.previewHeights, ...heights };
            }, false);
        });
        for (const stage of ['detection', 'segmentation']) {
            const title = stage === 'detection' ? 'Detection preview' : 'Segmentation preview';
            const preview = createDOMPreviewController(controller.node, { noWidget: true, freeResize: true, label: title });
            const body = element('div');
            const canvas = element('div');
            canvas.setAttribute('aria-label', `${title} size`);
            canvas.dataset.previewStage = stage;
            canvas.style.cssText = 'height:240px;min-height:120px;resize:vertical;overflow:hidden;max-width:100%;';
            canvas.append(preview.container);
            // Keep the same description before/after execution so an already
            // open section does not grow when a result or review stop arrives.
            const note = element('div', 'en-panel-note', stage === 'detection'
                ? 'Selected boxes before SAM2 and mask refinement.' : 'Green shows the final mask used for detailing.');
            body.append(canvas, note);
            preview.img.alt = title;
            this.stages[stage] = { title, preview, body, note, canvas };
        }
        this.restoreHeights();
    }
    restoreHeights() {
        // Loading or undoing editor state must not be recorded as a new resize.
        this.observer.disconnect();
        for (const [stage, { canvas }] of Object.entries(this.stages)) {
            canvas.style.height = `${previewHeight(this.controller.state.editor.previewHeights?.[stage])}px`;
            this.observer.observe(canvas, { attributes: true, attributeFilter: ['style'] });
        }
    }
    section(form, parent, stage) {
        const item = this.stages[stage];
        form.section(parent, `${stage}_preview`, item.title, body => body.append(item.body), header => {
            const key = `stop_${stage}`, enabled = form.state.config.parameters[key];
            const stop = button('■', `Stop after ${stage}`, () => form.edit(state => { state.config.parameters[key] = !enabled; }));
            stop.title = form.state.spec.fields[key].tooltip;
            stop.setAttribute('aria-pressed', String(enabled)); stop.dataset.field = key;
            header.append(stop);
        });
    }
    summary(key) {
        const stage = key.replace('_preview', ''), item = this.stages[stage];
        if (!item) return null;
        const enabled = this.controller.state.config.parameters[`stop_${stage}`];
        return [enabled ? 'Stop on' : 'Stop off', item.status?.paused ? 'Review · queue to continue' :
            item.status ? `${item.status.counts.reduce((a, b) => a + b, 0)} regions` : 'Not run'].join(' · ');
    }
    update(output) {
        if (this.controller.disposed) return;
        let paused;
        for (const [stage, item] of Object.entries(this.stages)) {
            const images = output?.[`eclipse_detailer_${stage}`], status = output?.[`eclipse_detailer_${stage}_status`]?.[0];
            if (!Array.isArray(images)) continue;
            setDOMPreviewController(item.preview, images);
            item.status = status;
            if (status?.paused) paused = `${stage}_preview`;
        }
        if (paused && !this.controller.state.sectionOpen(paused)) {
            this.controller.edit(state => state.toggleSection(paused));
        } else this.controller.form.syncSummaries();
        this.controller.measure();
    }
    dispose() {
        this.observer.disconnect();
        for (const item of Object.values(this.stages)) item.preview.dispose();
    }
}
