/** Detailer live frames and final images share one locally controlled preview. */
import { app, api, revokeNodePreview, clearNodeOutputImages } from './comfy/index.js';
import { createDOMPreview, setDOMPreviewController } from './eclipse-dom-preview.js';

const previews = new WeakMap(), activePreviews = new Set();

function suppressNativePreview(node) {
    revokeNodePreview(node);
    clearNodeOutputImages(node);
    node.imgs = undefined; node.images = undefined; node.preview = undefined; node.imageIndex = null;
    for (const widget of [...(node.widgets ?? [])]) {
        if (widget.name === '$$canvas-image-preview') node.removeWidget(widget);
    }
    node.setDirtyCanvas(true, true);
}

export class DetailerPreview {
    constructor(controller) {
        this.controller = controller; this.node = controller.node;
        this.element = document.createElement('div');
        this.element.className = 'en-review-preview-content';
        this.element.setAttribute('aria-label', 'Detailed image preview');
        this.element.style.position = 'relative';
        const final = createDOMPreview(this.node, { noWidget: true, freeResize: true, minHeight: 100, label: 'Detailed image preview' });
        this.final = this.node._eclipseDomPreview;
        this.final.img.alt = 'Detailed image';
        this.final.img.style.width = '100%'; this.final.img.style.height = '100%';
        final.style.background = 'transparent';
        this.live = document.createElement('img'); this.live.alt = 'Live detailed image'; this.live.draggable = false;
        this.live.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:contain;display:none;';
        this.element.append(final, this.live);
        previews.set(this.node, this);
        this.sync();
    }
    get visible() {
        return !this.controller.invalid && this.controller.state.config.parameters.live_preview
            && !!(this.liveUrl || this.final.state.images.length);
    }
    sync() {
        if (this.disposed) return;
        this.element.style.display = this.visible ? 'block' : 'none';
        this.final.state.hidden = !this.visible;
        this.final.container.style.display = this.liveUrl ? 'none' : 'flex';
        this.live.style.display = this.liveUrl ? 'block' : 'none';
        this.controller.measure();
    }
    showLive(blob, jobId) {
        if (this.disposed) return;
        this.releaseLive();
        // Own a separate URL: ComfyUI's sidebar and node store own their URLs.
        this.liveUrl = URL.createObjectURL(blob); this.jobId = jobId;
        activePreviews.add(this);
        this.live.src = this.liveUrl;
        this.sync();
    }
    releaseLive() {
        this.live.removeAttribute('src');
        if (this.liveUrl) URL.revokeObjectURL(this.liveUrl);
        this.liveUrl = null; this.jobId = null;
        activePreviews.delete(this);
    }
    complete(output) {
        if (this.disposed) return;
        this.releaseLive();
        // A run with Preview off has no new preview files. Keep the last
        // available images so turning it on again does not require a queue.
        if (Array.isArray(output?.images) && (output.images.length || this.controller.state.config.parameters.live_preview)) {
            setDOMPreviewController(this.final, output.images);
        }
        suppressNativePreview(this.node);
        this.sync();
    }
    finish(jobId) {
        if (!this.liveUrl || this.jobId !== jobId) return;
        this.releaseLive(); suppressNativePreview(this.node); this.sync();
    }
    dispose() {
        if (this.disposed) return;
        this.disposed = true; this.releaseLive(); this.final.dispose(); previews.delete(this.node);
    }
}

export function installDetailerPreviews() {
    const live = ({ detail }) => {
        let graph = app.rootGraph ?? app.graph, node;
        // Execution IDs describe the full nested path; local IDs can collide.
        for (const id of String(detail.displayNodeId).split(':')) {
            node = graph?.getNodeById(id); graph = node?.subgraph;
        }
        const preview = previews.get(node);
        if (!preview) return;
        preview.showLive(detail.blob, detail.jobId);
        // Retire the native node preview after all listeners have handled this
        // event, without releasing the sidebar's shared reference.
        queueMicrotask(() => { if (!preview.disposed) suppressNativePreview(node); });
    };
    const finished = ({ detail }) => { for (const preview of activePreviews) preview.finish(detail.prompt_id); };
    api.addEventListener('b_preview_with_metadata', live);
    const endings = ['execution_success', 'execution_error', 'execution_interrupted'];
    for (const event of endings) api.addEventListener(event, finished);
    return () => {
        api.removeEventListener('b_preview_with_metadata', live);
        for (const event of endings) api.removeEventListener(event, finished);
    };
}
