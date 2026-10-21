/** Themed Load/Preview Video hosts with shared media processing. */
import { app, api } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { button, element, ensurePanelStyle } from './eclipse-panel-controls.js';
import { numericInputValue } from './eclipse-linked-numbers.js';
import { createVideoEditor } from './eclipse-video-playlist.js';
import { attachVideoPreview, setVideoPreviewSource, stopVideoPreview } from './eclipse-video-preview-common.js';
import { isConfiguringGraph } from './eclipse-widget-utils.js';

const IDS = ['Load Video [Eclipse Nova]', 'Preview Video [Eclipse Nova]'];
const WIDGETS = ['ECLIPSE_NOVA_LOAD_VIDEO', 'ECLIPSE_NOVA_PREVIEW_VIDEO'];
const controllers = new WeakMap();

export class VideoState {
    constructor(raw, spec, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : structuredClone(raw); this.spec = spec;
        const c = this.config, load = spec.kind === 'load';
        const fields = load ? ['version', 'clips', 'width', 'height', 'fit', 'timing_mode', 'fps'] : ['version', 'fps', 'stop'];
        const bounded = (value, min, max) => typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
        if (!c || Array.isArray(c) || Object.keys(c).length !== fields.length || fields.some(key => !Object.hasOwn(c, key))
            || c.version !== 1 || !bounded(c.fps, 1, load ? 240 : 120)) throw Error('Invalid video configuration.');
        if (load) {
            if (!['pad', 'crop', 'stretch'].includes(c.fit) || !['source', 'fixed'].includes(c.timing_mode)
                || ['width', 'height'].some(key => !bounded(c[key], 0, 16384) || !Number.isInteger(c[key]))
                || !Array.isArray(c.clips) || c.clips.length > 128) throw Error('Invalid video settings or playlist.');
            const ids = new Set(); let metadata = 0;
            for (const row of c.clips) {
                if (!row || typeof row.id !== 'string' || !row.id || row.id.length > 128 || ids.has(row.id)
                    || (row.file !== null && (!row.file || !['input', 'output'].includes(row.file.type)
                    || typeof row.file.filename !== 'string' || !row.file.filename || /[/\\\0]/.test(row.file.filename)
                    || typeof row.file.subfolder !== 'string' || /[\\\0]/.test(row.file.subfolder)
                    || (row.file.subfolder && row.file.subfolder.split('/').some(part => ['', '.', '..'].includes(part)))))
                    || ['start_frame', 'load_cap'].some(key => !bounded(row[key], 0, 2 ** 31 - 1) || !Number.isInteger(row[key]))
                    || ['enabled', 'mute', 'use_metadata'].some(key => typeof row[key] !== 'boolean')
                    || (row.use_metadata && (!row.enabled || row.file === null))) throw Error('Invalid video clip.');
                ids.add(row.id); metadata += Number(row.use_metadata);
            }
            if (metadata > 1) throw Error('Select at most one metadata source.');
        } else if (typeof c.stop !== 'boolean') throw Error('Stop must be enabled or disabled.');
        this.editor = { barCollapsed: editor.barCollapsed === true, sizeOpen: editor.sizeOpen === true };
    }
    value() { return JSON.stringify(this.config); }
}

class VideoForm {
    constructor(controller) {
        this.controller = controller; this.load = controller.spec.kind === 'load';
        this.controls = element('div', 'en-panel-content'); this.controls.style.flex = '0 0 auto';
        if (this.load) this.controls.classList.add('en-video-global');
        if (this.load) {
            this.playlist = createVideoEditor(controller.node, {
                playlist: () => JSON.stringify({ version: 1, clips: this.config.clips }),
                save: clips => controller.edit(state => { state.config.clips = clips; }, false),
                options: () => this.previewOptions(), measure: () => controller.measure(),
            });
        } else {
            this.preview = attachVideoPreview(controller.node, { sourceType: 'temp' });
            this.preview.classList.add('en-review-preview-content'); this.preview.style.height = '';
            this.preview.setAttribute('aria-label', 'Video preview'); controller.node._eclipse_videoEl.setAttribute('aria-label', 'Preview video');
        }
    }
    get config() { return this.controller.state.config; }
    get state() { return this.controller.state; }
    connected(name) { return this.controller.node.inputs?.find(input => input.name === name)?.link != null; }
    sourceTimed() {
        const node = this.controller.node, slot = node.inputs?.findIndex(input => input.name === 'images');
        const type = slot >= 0 && node.graph ? node.getInputLink?.(slot)?.type : null;
        return ['VIDEO', 'ECLIPSE_FRAME_TIMELINE'].includes(type);
    }
    previewOptions() {
        const result = { width: this.config.width, height: this.config.height, fit: this.config.fit,
            timing_mode: this.config.timing_mode, fps: this.config.fps };
        for (const name of ['width', 'height', ...(result.timing_mode === 'fixed' ? ['fps'] : [])]) {
            if (!this.connected(name)) continue;
            const value = numericInputValue(this.controller.node, name);
            if (value == null) throw Error(`Connected ${name} needs execution. Queue the node to build its video with the resolved input.`);
            result[name] = value;
        }
        return result;
    }
    change(action, render = true) {
        this.controller.edit(action, render); this.playlist?.settingsChanged();
    }
    render() {
        const { root } = this.controller;
        this.controls.replaceChildren();
        const bar = this.bar(this.controls);
        if (this.load) {
            if (this.config.timing_mode === 'fixed' && !this.state.editor.barCollapsed) this.number(bar, 'fps', 'FPS', 1, 240, 0.1);
            this.sizeSection(this.controls);
        } else if (!this.sourceTimed()) {
            const grid = element('div', 'en-panel-grid'); this.number(grid, 'fps', 'FPS', 1, 120, 0.1); this.controls.append(grid);
        } else this.controls.append(element('div', 'en-panel-note', 'Source timing and dimensions are retained.'));
        const content = element('div', 'en-panel-content'); content.append(this.controls, this.load ? this.playlist.element : this.preview);
        root.replaceChildren(content); this.controller.measure();
    }
    bar(parent) {
        const collapsed = this.state.editor.barCollapsed, title = this.load ? 'Timing' : 'Mode';
        const bar = element('div', 'en-panel-bar en-panel-with-run'); bar.dataset.collapsed = String(collapsed);
        bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', title);
        const disclosure = button('', title, () => this.controller.edit(state => { state.editor.barCollapsed = !collapsed; }));
        disclosure.className = 'en-panel-disclosure'; disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', `${title}:`));
        if (collapsed) disclosure.append(element('span', 'en-panel-summary', this.load ? this.config.timing_mode === 'source' ? 'Source' : 'Fixed FPS' : `Stop ${this.config.stop ? 'on' : 'off'}`));
        bar.append(disclosure);
        if (!collapsed && this.load) for (const [key, title] of [['source', 'Source'], ['fixed', 'Fixed FPS']]) {
            const choice = button(title, `${title} timing`, () => this.change(state => { state.config.timing_mode = key; }));
            choice.title = key === 'source' ? 'Retain every original frame duration, including mixed frame rates.' : 'Duplicate/drop frames onto the selected FPS grid.';
            choice.setAttribute('aria-pressed', String(this.config.timing_mode === key)); bar.append(choice);
        }
        if (!collapsed && !this.load) {
            const actions = element('div', 'en-panel-run-actions');
            const stop = button('■', 'Stop', () => this.change(state => { state.config.stop = !state.config.stop; }));
            stop.setAttribute('aria-pressed', String(this.config.stop)); stop.title = 'Review changed inputs here. Queue unchanged again to continue downstream.';
            const cancel = button('×', 'Stop current execution', async () => {
                try { await api.interrupt(null); }
                catch (error) { app.extensionManager.toast.add({ severity: 'error', summary: 'Could not stop execution', detail: error.message }); }
            });
            actions.append(stop, cancel); bar.append(actions);
        }
        parent.append(bar);
        return bar;
    }
    sizeSection(parent) {
        const open = this.state.editor.sizeOpen, section = element('section', 'en-panel-section'); section.setAttribute('aria-label', 'Output size');
        const header = element('div', 'en-panel-section-header');
        const toggle = button('', 'Output size', () => this.controller.edit(state => { state.editor.sizeOpen = !open; }));
        toggle.className = 'en-panel-section-toggle'; toggle.setAttribute('aria-expanded', String(open));
        this.summary = element('span', 'en-panel-summary');
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} Output size`), this.summary);
        header.append(toggle); section.append(header);
        if (open) {
            const body = element('div', 'en-panel-section-body'), grid = element('div', 'en-panel-grid');
            this.number(grid, 'width', 'Width', 0, 16384, 1); this.number(grid, 'height', 'Height', 0, 16384, 1);
            const fit = element('div', 'en-panel-bar'); fit.setAttribute('role', 'group'); fit.setAttribute('aria-label', 'Fit');
            fit.append(element('span', 'en-panel-bar-label', 'Fit:'));
            for (const key of ['pad', 'crop', 'stretch']) {
                const choice = button(key[0].toUpperCase() + key.slice(1), `${key} fit`, () => this.change(state => { state.config.fit = key; }));
                choice.setAttribute('aria-pressed', String(this.config.fit === key)); fit.append(choice);
            }
            body.append(grid, fit, element('div', 'en-panel-note', '0 = automatic. Connected width/height override local values.')); section.append(body);
        }
        parent.append(section); this.syncSummaries();
    }
    number(parent, key, title, min, max, step) {
        const label = element('label', 'en-panel-field'), input = element('input'), linked = this.connected(key);
        label.append(element('span', '', title + (linked ? ' · input' : '')));
        input.type = 'number'; input.min = min; input.max = max; input.step = step; input.value = this.config[key]; input.disabled = linked;
        input.setAttribute('aria-label', title); input.title = linked ? 'Connected input overrides the local value.' : title;
        input.oninput = () => {
            if (input.checkValidity() && Number.isFinite(input.valueAsNumber)) this.change(state => { state.config[key] = input.valueAsNumber; }, false);
        };
        input.onchange = () => { input.value = this.config[key]; }; label.append(input); parent.append(label);
    }
    syncSummaries() {
        if (!this.summary) return;
        const value = key => this.connected(key) ? `${key} input` : this.config[key] || 'Auto';
        this.summary.textContent = `${value('width')} × ${value('height')} · ${this.config.fit}`;
    }
    restore() {
        this.playlist?.restore();
        if (!this.load) {
            const result = this.controller.node.properties?.eclipseVideoPreviewResult;
            if (result) setVideoPreviewSource(this.controller.node, result);
        }
    }
    executed(output) {
        if (this.playlist) { this.playlist.executed(output); return; }
        const result = output?.eclipse_video?.[0];
        this.controller.node.properties ??= {}; this.controller.node.properties.eclipseVideoPreviewResult = result ?? null;
        if (result) setVideoPreviewSource(this.controller.node, result);
        else {
            const video = this.controller.node._eclipse_videoEl; video.pause(); video.removeAttribute('src'); video.load(); video.style.display = 'none';
        }
    }
    dispose() { this.playlist?.close(); }
    destroy() { this.playlist?.destroy(); if (!this.load) stopVideoPreview(this.controller.node); }
}

class VideoPanel extends ConfigurationPanel {
    constructor(node, name, options) {
        super(node, name, options, {
            State: VideoState, Form: VideoForm, widgetType: options.editorSpec.kind === 'load' ? WIDGETS[0] : WIDGETS[1],
            editorKey: 'eclipseVideoPanel', className: 'en-video-panel', label: options.editorSpec.kind === 'load' ? 'Load Video editor' : 'Preview Video editor',
            fillHeight: true, minHeight: 200,
            onDispose: node => { controllers.get(node)?.form.destroy(); controllers.delete(node); },
        });
        this.widget.options.socketless = true;
        this.observer = new ResizeObserver(() => this.measure()); this.observer.observe(this.form.controls);
        if (this.form.playlist) this.observer.observe(this.form.playlist.controls);
    }
    measure() {
        this.numbers?.sync();
        if (this.disposed || this.frame) return;
        this.frame = requestAnimationFrame(() => {
            this.frame = null; if (!this.root.isConnected || !this.root.offsetWidth) return;
            const top = this.form?.controls.offsetHeight ?? 0;
            // The scrollable clip list and stretched player are allocations,
            // never minimum-height measurements. Only fixed controls reserve space.
            const height = Math.ceil(top + (this.form?.playlist?.minimumHeight() ?? 100) + (this.form?.load ? 24 : 0));
            const minWidth = this.form?.load ? 640 : 360;
            if (height === this.height && this.node.size[0] >= minWidth) return;
            this.height = height; this.profile.minHeight = height;
            this.root.style.setProperty('--comfy-widget-min-height', `${height}px`);
            const size = this.node.computeSize(); this.node.setSize([Math.max(this.node.size[0], minWidth), Math.max(this.node.size[1], size[1])]);
            this.node.setDirtyCanvas(true, true);
        });
    }
}

app.registerExtension({
    name: 'EclipseNova.VideoPanels',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return Object.fromEntries(WIDGETS.map(type => [type, (node, name, inputData) => {
            const controller = new VideoPanel(node, name, inputData[1]); controllers.set(node, controller);
            return { widget: controller.widget, minWidth: controller.form.load ? 640 : 360, minHeight: controller.form.load ? 560 : 370 };
        }]));
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (!IDS.includes(data.name)) return;
        if (data.name === IDS[0]) {
            const created = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function (...args) {
                const result = created?.apply(this, args);
                if (!isConfiguringGraph()) this.setSize([860, 600]);
                return result;
            };
        }
        for (const method of ['onConfigure', 'onAdded', 'onGraphConfigured', 'onConnectionsChange']) {
            const original = nodeType.prototype[method];
            nodeType.prototype[method] = function (...args) {
                const result = original?.apply(this, args), controller = controllers.get(this);
                if (controller) {
                    if (method === 'onConfigure') { controller.restore(controller.value()); if (!controller.invalid) controller.form.restore(); }
                    else if (!controller.invalid) controller.form.render();
                    if (method === 'onConnectionsChange') controller.form.playlist?.settingsChanged();
                    controller.bindHost();
                }
                return result;
            };
        }
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (output) {
            const result = executed?.apply(this, arguments); controllers.get(this)?.form.executed(output); return result;
        };
    },
});
