/** Single DOM configuration/preview host for both ComfyUI canvases. */
import { app } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { attachVideoPreview, setVideoPreviewSource, stopVideoPreview } from './eclipse-video-preview-common.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, SaveVideoState } from './eclipse-save-video-state.js';
import { SaveVideoForm } from './eclipse-save-video-form.js';

const controllers = new WeakMap();

class SaveVideoPanel extends ConfigurationPanel {
    constructor(node, name, options) {
        super(node, name, options, {
            State: SaveVideoState, Form: SaveVideoForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
            className: 'en-save-video', label: 'Save Video editor', fillHeight: true, minHeight: 300,
            onDispose: node => { stopVideoPreview(node); controllers.delete(node); },
        });
        this.widget.options.socketless = true;
        this.observer = new ResizeObserver(() => this.measure()); this.observer.observe(this.form.controls);
    }
    source() {
        const inputs = this.node.inputs ?? [], index = inputs.findIndex(input => input.name === 'images');
        const type = this.node.graph && index >= 0 ? this.node.getInputLink?.(index)?.type : null;
        if (type === 'VIDEO') return 'video';
        if (type === 'ECLIPSE_FRAME_TIMELINE') return 'timeline';
        return inputs.some(input => input.name === 'timing_opt' && input.link != null) ? 'timed' : 'image';
    }
    mountPreview() {
        if (this.preview || this.disposed) return;
        this.preview = attachVideoPreview(this.node);
        this.preview.classList.add('en-review-preview-content'); this.preview.style.height = '';
        this.preview.setAttribute('aria-label', 'Saved video preview');
        this.node._eclipse_videoEl.setAttribute('aria-label', 'Saved video');
        this.node.hideOutputImages = true; this.form.render();
    }
    syncPreview() {
        if (!this.preview) return;
        const visible = this.state.config.options.show_preview;
        this.preview.style.display = visible ? 'flex' : 'none';
        if (!visible) this.node._eclipse_videoEl?.pause();
    }
    executed(output) {
        const info = output?.eclipse_video?.[0];
        if (info && this.state.config.options.show_preview) setVideoPreviewSource(this.node, info);
        else {
            const video = this.node._eclipse_videoEl;
            video?.pause(); video?.removeAttribute('src'); video?.load();
            if (video) video.style.display = 'none';
        }
    }
    measure() {
        if (this.disposed || this.frame) return;
        this.frame = requestAnimationFrame(() => {
            this.frame = null; if (!this.root.isConnected || !this.root.offsetWidth) return;
            const preview = !this.invalid && this.state.config.options.show_preview;
            const controls = this.invalid ? this.root.firstElementChild : this.form.controls;
            const height = Math.ceil((controls?.offsetHeight ?? 0) + 16 + (preview ? 116 : 0));
            if (height <= 16 || (height === this.height && preview === this.measuredPreview)) return;
            this.height = height; this.profile.minHeight = height; this.measuredPreview = preview;
            this.root.style.setProperty('--comfy-widget-min-height', `${height}px`);
            const size = this.node.computeSize();
            this.node.setSize([Math.max(340, this.node.size[0]), preview ? Math.max(this.node.size[1], size[1]) : size[1]]);
            this.node.setDirtyCanvas(true, true);
        });
    }
}

app.registerExtension({
    name: 'EclipseNova.SaveVideoPanel',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new SaveVideoPanel(node, name, inputData[1]); controllers.set(node, controller);
            return { widget: controller.widget, minWidth: 420, minHeight: 410 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== NODE_ID) return;
        const created = nodeType.prototype.onNodeCreated, executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args); controllers.get(this)?.mountPreview(); return result;
        };
        for (const method of ['onConfigure', 'onAdded', 'onGraphConfigured', 'onConnectionsChange']) {
            const original = nodeType.prototype[method];
            nodeType.prototype[method] = function (...args) {
                const result = original?.apply(this, args), controller = controllers.get(this);
                if (controller) {
                    if (method === 'onConfigure') controller.restore(controller.value());
                    else if (!controller.invalid) controller.form.render();
                    controller.bindHost();
                }
                return result;
            };
        }
        nodeType.prototype.onExecuted = function (output) {
            const result = executed?.apply(this, arguments); controllers.get(this)?.executed(output); return result;
        };
    },
});
