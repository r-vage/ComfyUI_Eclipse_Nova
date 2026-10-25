/** Image Selector / Comparer panels using Nova's shared DOM design in both canvases. */
import { app, api } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { element, button, ensurePanelStyle } from './eclipse-panel-controls.js';
import { runActions } from './eclipse-panel-run.js';

export const WIDGET_TYPE = 'ECLIPSE_NOVA_IMAGE_REVIEW';
export const SELECTOR_ID = 'Image Selector [Eclipse Nova]';
export const COMPARER_ID = 'Image Comparer [Eclipse Nova]';
const EDITOR_KEY = 'eclipseImageReview';
const controllers = new WeakMap();
const imageURL = data => api.apiURL(`/view?${new URLSearchParams({
    filename: data.filename, subfolder: data.subfolder || '', type: data.type || 'temp',
})}`);

export class ImageReviewState {
    constructor(raw, spec, editor = {}) {
        const config = typeof raw === 'string' ? JSON.parse(raw) : structuredClone(raw);
        const selector = spec.kind === 'selector';
        const fields = selector ? ['version', 'auto_confirm', 'trigger'] : ['version', 'output'];
        if (!config || Array.isArray(config) || Object.keys(config).length !== fields.length
            || !fields.every(key => Object.hasOwn(config, key)) || config.version !== 1
            || (selector ? typeof config.auto_confirm !== 'boolean' || !Number.isInteger(config.trigger)
                || config.trigger < 0 || config.trigger > 2147483647
                : !['a', 'b'].includes(config.output))) {
            throw Error('Invalid image review configuration.');
        }
        this.config = config;
        this.editor = {
            modeCollapsed: editor.modeCollapsed === true,
            mode: editor.mode === 'Click' ? 'Click' : 'Slide',
            pair: Number.isSafeInteger(editor.pair) && editor.pair >= 0 ? editor.pair : 0,
        };
    }
    value() { return JSON.stringify(this.config); }
}

function modeBar(controller, key, label, summary, options) {
    const bar = element('div', 'en-panel-bar'), collapsed = controller.state.editor[key];
    bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', label);
    const disclosure = button('', label, () => controller.edit(state => { state.editor[key] = !collapsed; }));
    disclosure.className = 'en-panel-disclosure'; disclosure.setAttribute('aria-expanded', String(!collapsed));
    disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', `${label}:`));
    bar.append(disclosure);
    if (collapsed) disclosure.append(element('span', 'en-panel-summary', summary));
    else for (const option of options) {
        const control = button(option.label, option.title || option.label, option.action);
        control.setAttribute('aria-pressed', String(option.selected)); bar.append(control);
    }
    return bar;
}

class SelectorForm {
    constructor(controller) {
        this.controller = controller;
        this.preview = element('div', 'en-selector-preview', 'Run workflow to load images');
        this.preview.setAttribute('aria-label', 'Image selection');
    }
    render() {
        const { root } = this.controller;
        this.content ??= element('div', 'en-panel-content');
        this.barHost ??= element('div');
        this.content.replaceChildren(this.barHost, this.preview);
        root.replaceChildren(this.content); this.syncSummaries();
    }
    syncSummaries() {
        const c = this.controller, enabled = c.state.config.auto_confirm;
        const bar = modeBar(c, 'modeCollapsed', 'Mode', enabled ? 'Auto confirm' : 'Manual selection', [{
            label: 'Auto confirm', selected: enabled,
            title: 'Auto confirm',
            action: () => {
                if (c.node._eclipseSelectorSetAutoSelection) c.node._eclipseSelectorSetAutoSelection(!enabled);
                else c.edit(state => { state.config.auto_confirm = !enabled; }, false);
            },
        }]);
        bar.classList.add('en-panel-with-run');
        bar.append(runActions(c));
        bar.title = 'Auto confirm selects all incoming images without pausing. Discard or loading a workflow turns it off.';
        this.barHost.replaceChildren(bar);
    }
    dispose() {}
    destroy() { this.preview.replaceChildren(); }
}

class ComparerForm {
    constructor(controller) {
        this.controller = controller;
        this.images = { a: [], b: [] }; this.selected = { a: null, b: null };
        this.requests = { a: 0, b: 0 }; this.loaded = { a: false, b: false };
        this.preview = element('div', 'en-comparer-preview');
        this.preview.setAttribute('aria-label', 'Image comparison');
        this.preview.tabIndex = 0;
        this.placeholder = element('span', 'en-comparer-empty', 'Run workflow to compare images');
        this.imgB = element('img'); this.imgA = element('img');
        this.imgA.alt = 'Image A'; this.imgB.alt = 'Image B';
        for (const img of [this.imgA, this.imgB]) { img.draggable = false; img.hidden = true; }
        this.slider = element('div', 'en-comparer-slider'); this.slider.hidden = true;
        this.dimA = element('span', 'en-comparer-dimension en-comparer-dimension-a');
        this.dimB = element('span', 'en-comparer-dimension en-comparer-dimension-b');
        this.preview.append(this.placeholder, this.imgB, this.imgA, this.slider, this.dimA, this.dimB);
        this.position = 50; this.over = false; this.down = false;
        this.preview.onpointerenter = () => { this.over = true; this.applyMode(); };
        this.preview.onpointermove = event => {
            const rect = this.preview.getBoundingClientRect();
            if (rect.width) this.position = Math.max(0, Math.min(100, (event.clientX - rect.left) / rect.width * 100));
            this.applyMode();
        };
        this.preview.onpointerdown = event => {
            if (event.button !== 0) return;
            event.preventDefault(); this.preview.focus({ preventScroll: true });
            this.down = true; this.applyMode();
        };
        this.preview.onpointerup = () => { this.down = false; this.applyMode(); };
        this.preview.onpointerleave = this.preview.onpointercancel = () => {
            this.over = false; this.down = false; this.applyMode();
        };
        this.preview.onkeydown = event => {
            if (['ArrowLeft', 'ArrowRight'].includes(event.key)) {
                event.preventDefault(); this.selectPair(this.pair + (event.key === 'ArrowLeft' ? -1 : 1), true);
            } else if (event.key === ' ' && controller.state.editor.mode === 'Click') {
                event.preventDefault(); this.down = true; this.applyMode();
            }
        };
        this.preview.onkeyup = this.preview.onblur = () => { this.down = false; this.applyMode(); };
        this.navigator = element('div', 'en-comparer-navigation');
        this.navigator.setAttribute('aria-label', 'Image pairs');
        this.observer = new ResizeObserver(() => this.renderNavigator()); this.observer.observe(controller.root);
    }
    render() {
        const c = this.controller, config = c.state.config;
        const content = element('div', 'en-panel-content');
        const bar = modeBar(c, 'modeCollapsed', 'Mode', `${c.state.editor.mode} · Output ${config.output.toUpperCase()}`, ['Slide', 'Click'].map(mode => ({
            label: mode, selected: c.state.editor.mode === mode,
            action: () => c.edit(state => { state.editor.mode = mode; }),
        })));
        if (!c.state.editor.modeCollapsed) {
            const output = element('div', 'en-comparer-output');
            output.setAttribute('role', 'group'); output.setAttribute('aria-label', 'Output');
            output.append(element('span', 'en-panel-bar-label', 'Output:'));
            for (const side of ['a', 'b']) {
                const control = button(side.toUpperCase(), `Output ${side.toUpperCase()}`, () => c.edit(state => { state.config.output = side; }));
                control.setAttribute('aria-pressed', String(config.output === side)); output.append(control);
            }
            bar.append(output);
        }
        content.append(bar, this.navigator, this.preview); c.root.replaceChildren(content);
        this.selectPair(c.state.editor.pair); this.applyMode();
    }
    get count() { return Math.max(this.images.a.length, this.images.b.length); }
    feed(output) {
        this.placeholder.textContent = 'Run workflow to compare images';
        this.images = { a: output.a_images || [], b: output.b_images || [] };
        const pair = Math.max(0, Math.min(this.count - 1, this.controller.state.editor.pair));
        if (pair !== this.controller.state.editor.pair) this.controller.edit(state => { state.editor.pair = pair; }, false);
        this.selectPair(this.controller.state.editor.pair);
    }
    expire() {
        this.images = { a: [], b: [] };
        this.controller.edit(state => {
            state.editor.pair = 0;
            delete this.controller.node.properties.eclipseComparerImages;
        }, false);
        this.selectPair(0);
        this.placeholder.textContent = 'Preview expired. Run workflow to reload images.';
    }
    loadImage(side, data) {
        const img = side === 'a' ? this.imgA : this.imgB, dim = side === 'a' ? this.dimA : this.dimB;
        const url = data ? imageURL(data) : null;
        if (url && img.getAttribute('src') === url) return;
        const request = ++this.requests[side];
        this.loaded[side] = false; dim.textContent = '';
        if (!url) { img.removeAttribute('src'); return; }
        img.src = url;
        // A previous pair's late load/error must not invalidate a newer result.
        const current = () => !this.destroyed && this.requests[side] === request;
        img.decode().then(() => {
            if (!current()) return;
            this.loaded[side] = true;
            dim.textContent = `${side.toUpperCase()}: ${img.naturalWidth} × ${img.naturalHeight}`;
            this.applyMode();
        }, () => { if (current()) this.expire(); });
    }
    selectPair(index, track = false) {
        const pair = Math.max(0, Math.min(this.count - 1, index));
        if (track) this.controller.edit(state => { state.editor.pair = pair; }, false);
        this.pair = pair;
        for (const side of ['a', 'b']) {
            const data = this.images[side][pair] || this.images[side][0] || null;
            this.selected[side] = data;
            this.loadImage(side, data);
        }
        this.placeholder.hidden = this.count > 0;
        this.applyMode(); this.renderNavigator();
    }
    applyMode() {
        const both = this.loaded.a && this.loaded.b, slide = this.controller.state.editor.mode === 'Slide';
        this.imgA.hidden = !this.loaded.a || (!slide && both && this.down);
        this.imgB.hidden = !this.loaded.b;
        this.imgA.style.clipPath = slide && both && this.over ? `inset(0 ${100 - this.position}% 0 0)` : '';
        this.slider.hidden = !(slide && both && this.over);
        this.slider.style.left = `${this.position}%`;
    }
    renderNavigator() {
        const nav = this.navigator; nav.replaceChildren(); nav.hidden = this.count <= 1;
        if (nav.hidden) return;
        const numberWidth = Math.max(26, String(this.count).length * 8 + 10);
        const capacity = Math.max(1, Math.floor(((this.controller.root.clientWidth || 320) - 100) / (numberWidth + 3)));
        const shown = Math.min(this.count, capacity), start = Math.max(0, Math.min(this.count - shown, this.pair - Math.floor(shown / 2)));
        const previous = button('‹', 'Previous pair', () => this.selectPair(this.pair - 1, true)); previous.disabled = this.pair === 0;
        nav.append(previous);
        for (let index = start; index < start + shown; index++) {
            const control = button(String(index + 1), `Pair ${index + 1} of ${this.count}`, () => this.selectPair(index, true));
            control.style.width = `${numberWidth}px`;
            control.setAttribute('aria-pressed', String(index === this.pair)); nav.append(control);
        }
        const next = button('›', 'Next pair', () => this.selectPair(this.pair + 1, true)); next.disabled = this.pair === this.count - 1;
        nav.append(next);
    }
    syncSummaries() {}
    dispose() {}
    destroy() {
        this.destroyed = true;
        this.observer.disconnect();
        for (const img of [this.imgA, this.imgB]) { img.onload = img.onerror = null; img.removeAttribute('src'); }
    }
    menu(options) {
        const actions = [];
        for (const side of ['a', 'b']) {
            const data = this.selected[side]; if (!data) continue;
            const label = side.toUpperCase(), url = imageURL(data);
            actions.push({ content: `Open Image ${label}`, callback: () => window.open(url, '_blank', 'noopener') });
            actions.push({ content: `Save Image ${label}`, callback: () => {
                const link = element('a'); link.href = url; link.download = data.filename; link.click();
            } });
        }
        options.unshift(...actions, ...(actions.length ? [null] : []));
    }
}

app.registerExtension({
    name: 'EclipseNova.ImageReviewPanels',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const selector = inputData[1].editorSpec.kind === 'selector';
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: ImageReviewState, Form: selector ? SelectorForm : ComparerForm,
                editorKey: EDITOR_KEY, widgetType: WIDGET_TYPE,
                className: selector ? 'en-image-selector' : 'en-image-comparer',
                label: selector ? 'Image Selector editor' : 'Image Comparer editor',
                fillHeight: true, minHeight: 240,
                onDispose: node => {
                    controllers.get(node)?.form.destroy(); controllers.delete(node);
                    delete node._eclipseSelectorPanel;
                },
            });
            controllers.set(node, controller);
            if (selector) node._eclipseSelectorPanel = controller;
            return { widget: controller.widget, minWidth: 340, minHeight: 430 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (![SELECTOR_ID, COMPARER_ID].includes(data.name)) return;
        const added = nodeType.prototype.onAdded;
        nodeType.prototype.onAdded = function (...args) {
            const result = added?.apply(this, args); controllers.get(this)?.bindHost(); return result;
        };
        // The selector extension owns pause/resume, snapshots and continuation.
        if (data.name === SELECTOR_ID) return;
        const configure = nodeType.prototype.onConfigure, executed = nodeType.prototype.onExecuted,
            menu = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configure?.apply(this, args), c = controllers.get(this);
            if (c) {
                c.restore(c.value()); c.bindHost();
                if (this.properties?.eclipseComparerImages) c.form.feed(this.properties.eclipseComparerImages);
            }
            return result;
        };
        nodeType.prototype.onExecuted = function (output) {
            const result = executed?.apply(this, arguments), c = controllers.get(this);
            if (c) {
                this.properties.eclipseComparerImages = { a_images: output.a_images || [], b_images: output.b_images || [] };
                c.form.feed(this.properties.eclipseComparerImages);
            }
            return result;
        };
        nodeType.prototype.getExtraMenuOptions = function (_canvas, options) {
            const result = menu?.apply(this, arguments); controllers.get(this)?.form.menu(options); return result;
        };
    },
});
