/** Load Audio's shared-design panel with explicit linked trim overrides. */
import { app, api } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { element, button, SearchMenu, ensurePanelStyle } from './eclipse-panel-controls.js';
import { createAudioPlayer, numericInputValue, uploadFile } from './eclipse-audio-player.js';
import { onVueModeChange } from './eclipse-widget-utils.js';

const NODE_ID = 'Load Audio [Eclipse Nova]';
const WIDGET_TYPE = 'ECLIPSE_NOVA_LOAD_AUDIO';
const EDITOR_KEY = 'eclipseLoadAudio';
const SOURCES = { Auto: 'Auto', 'Selected file': 'File', 'Incoming audio': 'Input' };
const controllers = new WeakMap();

export class AudioState {
    constructor(raw, _spec, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : structuredClone(raw);
        const value = this.config, fields = ['version', 'audio', 'source', 'start_time', 'duration', 'stop'];
        if (!value || Array.isArray(value) || Object.keys(value).length !== fields.length
            || fields.some(key => !Object.hasOwn(value, key)) || value.version !== 1
            || typeof value.audio !== 'string' || value.audio.length > 4096 || value.audio.includes('\0')
            || typeof value.source !== 'string' || !Object.hasOwn(SOURCES, value.source) || typeof value.stop !== 'boolean'
            || ['start_time', 'duration'].some(key => typeof value[key] !== 'number' || !Number.isFinite(value[key]) || value[key] < 0 || value[key] > 86400)) {
            throw Error('Invalid audio configuration.');
        }
        this.editor = { collapsed: editor.collapsed === true, trimOpen: editor.trimOpen !== false };
    }
    value() { return JSON.stringify(this.config); }
}

class AudioForm {
    constructor(controller) {
        this.controller = controller; this.menu = new SearchMenu(); this.request = 0;
        this.player = createAudioPlayer(controller.node, () => controller.state.config, { onChange: () => this.updateSummary() });
        this.player.element.classList.add('en-audio-player');
        this.unsubscribe = onVueModeChange(() => this.menu.close());
        this.fileInput = element('input'); this.fileInput.type = 'file'; this.fileInput.accept = 'audio/*,video/*'; this.fileInput.hidden = true;
        this.fileInput.onchange = () => { const file = this.fileInput.files?.[0]; if (file) void this.upload(file); this.fileInput.value = ''; };
        controller.root.ondragover = event => { if (event.dataTransfer?.types.includes('Files')) { event.preventDefault(); event.stopPropagation(); } };
        controller.root.ondrop = event => {
            const file = event.dataTransfer?.files[0]; if (!file) return;
            event.preventDefault(); event.stopPropagation(); void this.upload(file);
        };
    }
    get state() { return this.controller.state; }
    get config() { return this.state.config; }
    connected(name) { return this.controller.node.inputs?.find(input => input.name === name)?.link != null; }
    async openFiles(trigger) {
        if (this.menu.trigger === trigger) { this.menu.close(true); return; }
        const request = ++this.request; this.listAbort?.abort(); this.listAbort = new AbortController();
        trigger.setAttribute('aria-busy', 'true');
        try {
            const response = await api.fetchApi('/eclipse-nova/audio/files', { cache: 'no-store', signal: this.listAbort.signal });
            const data = await response.json(); if (!response.ok) throw Error(data.error ?? 'Unable to list audio files.');
            if (this.dead || request !== this.request || !trigger.isConnected) return;
            this.menu.open(trigger, 'Audio file', this.config.audio, data.files, name => {
                this.controller.edit(state => { state.config.audio = name; });
            });
        } catch (error) {
            if (!this.dead && request === this.request && error.name !== 'AbortError') this.setStatus(error.message);
        } finally { trigger.removeAttribute('aria-busy'); }
    }
    async upload(file) {
        if (this.uploading) return;
        this.uploading = true; this.setStatus('Uploading…');
        try {
            const name = await uploadFile(file);
            if (this.dead) return;
            this.status = '';
            this.controller.edit(state => { state.config.audio = name; });
        } catch (error) { if (!this.dead) this.setStatus(error.message); }
        finally { this.uploading = false; }
    }
    setStatus(message) { this.status = message; if (this.statusElement) this.statusElement.textContent = message; this.controller.measure(); }
    render() {
        this.menu.close();
        const { root } = this.controller, config = this.config, collapsed = this.state.editor.collapsed;
        const content = element('div', 'en-panel-content'), bar = element('div', 'en-panel-bar en-panel-with-run');
        bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Source');
        const disclosure = button('', 'Source', () => this.controller.edit(state => { state.editor.collapsed = !collapsed; }));
        disclosure.className = 'en-panel-disclosure'; disclosure.setAttribute('aria-expanded', String(!collapsed));
        disclosure.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Source:'));
        if (collapsed) disclosure.append(element('span', 'en-panel-summary', `${SOURCES[config.source]} · Stop ${config.stop ? 'on' : 'off'}`));
        bar.append(disclosure);
        if (!collapsed) {
            for (const [source, title] of Object.entries(SOURCES)) {
                const choice = button(title, source, () => this.controller.edit(state => { state.config.source = source; }));
                choice.setAttribute('aria-pressed', String(source === config.source)); bar.append(choice);
            }
            const actions = element('div', 'en-panel-run-actions');
            const stop = button('■', 'Stop', () => this.controller.edit(state => { state.config.stop = !state.config.stop; }));
            stop.setAttribute('aria-pressed', String(config.stop));
            stop.title = 'Stop normal queues here after changed inputs. Queue unchanged again to continue from the reviewed result.';
            actions.append(stop); bar.append(actions);
        }
        content.append(bar);
        const fileRow = element('div', 'en-audio-files');
        const file = button('', 'Audio file', () => void this.openFiles(file));
        file.className = 'en-panel-select'; file.setAttribute('role', 'combobox');
        file.setAttribute('aria-haspopup', 'listbox'); file.setAttribute('aria-expanded', 'false'); file.title = config.audio || 'Select a local audio or video file';
        file.append(element('span', '', config.audio || 'Select audio file…'), element('span', '', '▾'));
        file.onkeydown = event => { if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); void this.openFiles(file); } };
        fileRow.append(file, button('+', 'Upload audio or video', () => this.fileInput.click()));
        content.append(fileRow, this.fileInput);
        const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', 'Trim');
        const header = element('div', 'en-panel-section-header');
        const toggle = button('', 'Trim', () => this.controller.edit(state => { state.editor.trimOpen = !state.editor.trimOpen; }));
        toggle.className = 'en-panel-section-toggle'; toggle.setAttribute('aria-expanded', String(this.state.editor.trimOpen));
        this.summary = element('span', 'en-panel-summary');
        toggle.append(element('span', 'en-panel-section-label', `${this.state.editor.trimOpen ? '▾' : '▸'} Trim`), this.summary);
        header.append(toggle); section.append(header); this.fields = {};
        if (this.state.editor.trimOpen) {
            const body = element('div', 'en-panel-section-body'), grid = element('div', 'en-panel-grid');
            for (const [key, title] of [['start_time', 'Start (seconds)'], ['duration', 'Duration (seconds)']]) {
                const field = element('label', 'en-panel-field'), label = element('span', '', title);
                const input = element('input'); input.type = 'number'; input.min = '0'; input.max = '86400'; input.step = '0.01';
                input.setAttribute('aria-label', title); input.value = String(config[key]); input.disabled = this.connected(key);
                if (input.disabled) { label.textContent += ' · input'; input.title = 'A connected input overrides this local value. Disconnect it to edit.'; }
                input.onchange = () => {
                    const value = input.valueAsNumber;
                    if (!Number.isFinite(value) || value < 0 || value > 86400) { input.value = String(this.config[key]); return; }
                    this.controller.edit(state => { state.config[key] = value; }, false);
                };
                field.append(label, input); grid.append(field); this.fields[key] = input;
            }
            body.append(grid, element('div', 'en-panel-note', 'Duration 0 = to the end. Connected trim inputs take priority.'));
            section.append(body);
        }
        content.append(section, this.player.element);
        this.statusElement = element('div', 'en-panel-note', this.status ?? ''); this.statusElement.setAttribute('role', 'status');
        content.append(this.statusElement); root.replaceChildren(content); this.syncSummaries(); this.controller.measure();
    }
    updateSummary() {
        if (!this.summary) return;
        const values = ['start_time', 'duration'].map(name => this.connected(name) ? numericInputValue(this.controller.node, name) : this.config[name]);
        this.summary.textContent = `${values[0] == null ? 'Input start' : `${values[0]}s start`} · ${values[1] == null ? 'Input duration' : values[1] === 0 ? 'To end' : `${values[1]}s`}`;
    }
    syncSummaries() {
        this.updateSummary();
        this.player.refresh(true);
    }
    dispose() { this.request++; this.listAbort?.abort(); this.menu.close(); }
    destroy() { this.dead = true; this.dispose(); this.player.dispose(); this.unsubscribe(); }
}

app.registerExtension({
    name: 'EclipseNova.LoadAudioPanel',
    setup() { ensurePanelStyle(); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: AudioState, Form: AudioForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-load-audio', label: 'Load Audio editor',
                onDispose: node => { controllers.get(node)?.form.destroy(); controllers.delete(node); },
            });
            controllers.set(node, controller); node.previewMediaType = 'audio';
            return { widget: controller.widget, minWidth: 360, minHeight: 260 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== NODE_ID) return;
        const configured = nodeType.prototype.onConfigure, added = nodeType.prototype.onAdded,
            executed = nodeType.prototype.onExecuted, connections = nodeType.prototype.onConnectionsChange,
            graphConfigured = nodeType.prototype.onGraphConfigured;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configured?.apply(this, args), controller = controllers.get(this);
            if (controller) { controller.restore(controller.value()); controller.bindHost(); } return result;
        };
        nodeType.prototype.onAdded = function (...args) {
            const result = added?.apply(this, args), controller = controllers.get(this);
            controller?.bindHost(); controller?.form.player.resume(); return result;
        };
        nodeType.prototype.onGraphConfigured = function (...args) {
            const result = graphConfigured?.apply(this, args); controllers.get(this)?.form.player.restore(); return result;
        };
        nodeType.prototype.onExecuted = function (output) {
            const result = executed?.apply(this, arguments), form = controllers.get(this)?.form;
            form?.player.executed(output); form?.syncSummaries(); return result;
        };
        nodeType.prototype.onConnectionsChange = function (type, slot, ...rest) {
            const result = connections?.call(this, type, slot, ...rest), controller = controllers.get(this);
            controller?.form.player.connected(type, slot);
            if (type === 1) queueMicrotask(() => { if (controller && !controller.disposed) controller.form.render(); });
            return result;
        };
    },
});
