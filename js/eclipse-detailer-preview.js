/** Live sampler/detailer frames and completed sampler batches share one preview. */
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
        const detailer = controller.spec.profile === 'detailer';
        const label = detailer ? 'Detailed image preview' : 'Sampler image preview';
        this.element.setAttribute('aria-label', label);
        this.element.style.position = 'relative';
        const final = createDOMPreview(this.node, { noWidget: true, freeResize: true, minHeight: 100, label });
        this.final = this.node._eclipseDomPreview;
        this.final.img.alt = detailer ? 'Detailed image' : 'Sampled image';
        this.final.img.style.width = '100%'; this.final.img.style.height = '100%';
        final.style.background = 'transparent';
        this.live = this.createLiveImage();
        this.element.append(final, this.live);
        previews.set(this.node, this);
        this.sync();
    }
    get enabled() {
        const p = this.controller.state.config.parameters;
        if (this.effectivePreview && (this.effectivePreview.local !== p.preview_mode
            || this.effectivePreview.usePipe !== p.allow_overwrite)) this.effectivePreview = null;
        return this.controller.spec.profile === 'detailer' ? p.live_preview
            : this.effectivePreview?.enabled ?? p.preview_mode === 'Preview';
    }
    get visible() {
        return !this.controller.invalid && this.enabled
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
    createLiveImage() {
        const image = document.createElement('img');
        image.alt = this.controller.spec.profile === 'detailer' ? 'Live detailed image' : 'Live sampled image';
        image.draggable = false;
        image.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:contain;display:none;';
        return image;
    }
    showLive(blob, jobId) {
        if (this.disposed) return;
        if (this.jobId !== jobId) { this.releaseLive(); this.sync(); }
        this.jobId = jobId;
        activePreviews.add(this);
        // Decode one frame at a time, retaining only the newest waiting blob.
        // Keep the completed image / last valid frame on screen in the meantime.
        this.nextBlob = blob;
        this.decodeNext();
    }
    decodeNext() {
        if (this.pending || !this.nextBlob) return;
        const frame = { image: this.createLiveImage(), url: URL.createObjectURL(this.nextBlob) };
        this.nextBlob = null; this.pending = frame;
        // Own a separate URL: ComfyUI's sidebar and node store own their URLs.
        frame.image.src = frame.url;
        const finish = ready => {
            if (this.pending !== frame) return; // completed, cancelled or removed
            this.pending = null;
            if (ready) {
                const previous = this.live, previousUrl = this.liveUrl;
                previous.replaceWith(frame.image);
                this.live = frame.image; this.liveUrl = frame.url;
                this.sync();
                previous.removeAttribute('src');
                if (previousUrl) URL.revokeObjectURL(previousUrl);
            } else {
                frame.image.removeAttribute('src'); URL.revokeObjectURL(frame.url);
            }
            this.decodeNext();
        };
        frame.image.decode().then(() => finish(true), () => finish(false));
    }
    releaseLive() {
        const pending = this.pending;
        this.pending = null; this.nextBlob = null;
        if (pending) { pending.image.removeAttribute('src'); URL.revokeObjectURL(pending.url); }
        this.live.removeAttribute('src');
        if (this.liveUrl) URL.revokeObjectURL(this.liveUrl);
        this.liveUrl = null; this.jobId = null;
        activePreviews.delete(this);
    }
    complete(output) {
        if (this.disposed) return;
        this.releaseLive();
        const effective = output?.eclipse_preview_enabled?.[0];
        if (typeof effective === 'boolean') this.effectivePreview = {
            local: this.controller.state.config.parameters.preview_mode,
            usePipe: this.controller.state.config.parameters.allow_overwrite, enabled: effective,
        };
        // Detailers only show live frames, including when replaying an older
        // cached output that still contains final-image references.
        if (this.controller.spec.profile === 'detailer') {
            setDOMPreviewController(this.final, []);
        } else if (Array.isArray(output?.images) && (output.images.length || this.enabled)) {
            // Samplers keep completed images while Preview is off so turning
            // it on again does not require a queue.
            setDOMPreviewController(this.final, output.images);
        }
        suppressNativePreview(this.node);
        this.sync();
    }
    finish(jobId) {
        if (this.jobId !== jobId) return;
        this.releaseLive(); suppressNativePreview(this.node); this.sync();
    }
    dispose() {
        if (this.disposed) return;
        this.disposed = true; this.releaseLive(); this.final.dispose(); previews.delete(this.node);
    }
}

export function installDetailerPreviews(controllers) {
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
    const review = ({ detail }) => {
        let graph = app.rootGraph ?? app.graph, node;
        if (detail.workflow_id && graph?.id && detail.workflow_id !== graph.id) return;
        for (const id of String(detail.node_id).split(':')) {
            node = graph?.getNodeById(id); graph = node?.subgraph;
        }
        // Advanced Detailer reviews also run when no sampling preview exists.
        controllers.get(node)?.review?.update(detail.output);
    };
    api.addEventListener('eclipse-nova-detailer-review', review);
    return () => {
        api.removeEventListener('b_preview_with_metadata', live);
        api.removeEventListener('eclipse-nova-detailer-review', review);
        for (const event of endings) api.removeEventListener(event, finished);
    };
}
