/**
 * Eclipse Nova — review saved prompts and replace individual render parts.
 * SPDX-License-Identifier: Apache-2.0
 */
import { app, api } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { element, button, ensurePanelStyle } from './eclipse-panel-controls.js';
import { findSetterByName } from './eclipse-set-get-utils.js';

const NODE = 'Part Prompt Editor [Eclipse Nova]';
const WIDGET = 'ECLIPSE_NOVA_PART_PROMPTS';
const controllers = new WeakMap();
const emptyConfig = () => ({ version: 1, enabled: false, source: '', edits: {} });

export class PartPromptState {
    constructor(raw, _spec, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : JSON.parse(JSON.stringify(raw));
        // ComfyUI restores node properties through Vue proxies in both renderers.
        this.editor = JSON.parse(JSON.stringify(editor));
        const c = this.config;
        if (c?.version !== 1 || typeof c.enabled !== 'boolean' || typeof c.source !== 'string'
            || !c.edits || typeof c.edits !== 'object' || Array.isArray(c.edits)) throw Error('Invalid part prompt configuration.');
        if (this.editor.catalog && (!c.source || this.editor.catalog.source !== c.source
            || !Array.isArray(this.editor.catalog.parts))) this.editor = {};
    }
    value() { return JSON.stringify(this.config); }
    reset() { this.config = emptyConfig(); this.editor = {}; }
    load(catalog) {
        if (this.config.source !== catalog.source && Object.keys(this.config.edits).length) {
            throw Error('The saved prompt source changed. Use Read selected run to reload it and clear pending edits.');
        }
        this.config.source = catalog.source;
        if (catalog.revision) this.config.revision = catalog.revision;
        else delete this.config.revision;
        this.editor.catalog = catalog;
        if (!catalog.parts.some(p => p.part === this.editor.part)) this.editor.part = catalog.parts[0]?.part ?? 1;
        // A saved edited revision already contains these replacements.
        for (const p of catalog.parts) if (this.config.edits[p.part] === p.prompt) delete this.config.edits[p.part];
    }
    get part() { return this.editor.catalog?.parts.find(p => p.part === (this.editor.part ?? 1)); }
    stepPart(delta) {
        const parts = this.editor.catalog?.parts ?? [], index = parts.indexOf(this.part);
        if (index < 0) return;
        this.editor.part = parts[Math.max(0, Math.min(parts.length - 1, index + delta))].part;
    }
    setText(text) {
        const part = this.part;
        if (!part) return;
        if (text === part.prompt) delete this.config.edits[part.part];
        else this.config.edits[part.part] = text;
    }
}

function upstream(node, slot) {
    const graph = node?.graph, id = node?.inputs?.[slot]?.link;
    const link = graph?.links?.get?.(id) ?? graph?.links?.[id];
    return link ? { node: graph.getNodeById(link.origin_id), slot: link.origin_slot } : null;
}

function runLoader(node) {
    let source = upstream(node, node.inputs?.findIndex(i => i.name === 'run_path'));
    const visited = new Set();
    while (source?.node && !visited.has(source.node)) {
        const current = source.node; visited.add(current);
        if (current.type === 'Load Video Run [Eclipse Nova]' && source.slot === 7) {
            return current;
        }
        if (current.type === 'GetNode [Eclipse Nova]') {
            const setter = findSetterByName(current.graph, current.widgets?.[0]?.value)?.node;
            source = upstream(setter, 0);
        } else if (current.type === 'SetNode [Eclipse Nova]' || current.type === 'Reroute') {
            source = upstream(current, 0);
        } else return null;
    }
    return null;
}

export function selectedRun(node) { return runLoader(node)?.widgets.find(w => w.name === 'saved_run')?.value; }

function selectedVersion(node) {
    const loader = runLoader(node);
    return { saved_run: loader?.widgets.find(w => w.name === 'saved_run')?.value,
        backup: loader?.widgets.find(w => w.name === 'backup')?.value ?? 'Current run' };
}

class PartPromptForm {
    constructor(controller) {
        this.controller = controller; this.request = null; this.message = '';
        this.selectionChanged = ({ detail }) => {
            if (detail.loader === runLoader(controller.node)) this.reset();
        };
        this.updated = event => {
            if (this.live && !this.live.finished) return;
            const selection = selectedVersion(controller.node);
            if (selection.saved_run !== event.detail.saved_run || selection.backup !== 'Current run') return;
            if (event.detail.operation === 'restore') controller.edit(s => s.reset());
            void this.read(true);
        };
        this.progress = ({ detail }) => {
            const live = this.live;
            if (!live?.token || live.token !== detail?.token || live.prompt_id !== detail.prompt_id) return;
            if (detail.status === 'running' && live.state.editor.catalog?.parts[detail.index]) {
                live.state.editor.part = detail.index + 1;
            } else if (['complete', 'stopped'].includes(detail.status)) {
                live.finished = true;
            } else return;
            this.render();
        };
        this.ended = ({ type, detail }) => {
            if (!this.live || this.live.prompt_id !== detail?.prompt_id) return;
            this.live.finished = true;
            if (!this.live.state.editor.catalog) this.message = type === 'execution_success'
                ? 'This execution finished before a part prompt was available.' : 'The run ended before its prompts were ready.';
            this.render();
        };
    }
    get state() { return this.live?.state ?? this.controller.state; }
    leaveLive() {
        if (this.live) this.dismissed = this.live.prompt_id;
        this.live = null;
    }
    reset(message = 'Editor cleared.') {
        this.request?.abort(); this.request = null; this.leaveLive();
        this.message = message; this.controller.edit(s => s.reset());
    }
    receive(packet) {
        if (this.controller.disposed || packet.prompt_id === this.dismissed) return;
        if (this.live?.prompt_id !== packet.prompt_id || this.live.loop_id !== packet.loop_id) {
            this.request?.abort(); this.request = null;
            this.live = { prompt_id: packet.prompt_id, loop_id: packet.loop_id, state: new PartPromptState(emptyConfig()) };
            this.message = 'Preparing prompts for the new run…';
            this.controller.edit(s => s.reset());
        }
        if (!packet.catalog || this.live.token === packet.token) return;
        this.live.token = packet.token; this.live.state.load(packet.catalog);
        this.message = 'These prompts belong to the queued render. Read a saved run to edit its prompts.';
        this.render();
    }
    navigate(change) {
        if (this.live) { change(this.state); this.render(); }
        else this.controller.edit(change);
    }
    async read(refresh = false) {
        const selected = selectedVersion(this.controller.node);
        if (!selected.saved_run || selected.saved_run === '(no saved runs found)') {
            this.reset(selected.saved_run ? 'Choose a saved run in Load Video Run.' : 'Connect Load Video Run → run_path directly or through Get/Set.');
            return;
        }
        this.leaveLive();
        const previous = this.controller.state.editor.selection;
        if (previous && (previous.saved_run !== selected.saved_run || previous.backup !== selected.backup)) {
            this.controller.edit(s => s.reset());
        }
        this.request?.abort();
        const request = this.request = new AbortController();
        this.message = 'Reading saved prompts…'; this.render();
        try {
            const response = await api.fetchApi('/eclipse-nova/video_run/prompts', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(selected), signal: request.signal,
            });
            const data = await response.json();
            if (!response.ok) throw Error(data.error || 'Could not read saved prompts.');
            if (request.signal.aborted || this.controller.disposed) return;
            if (JSON.stringify(selectedVersion(this.controller.node)) !== JSON.stringify(selected)) throw Error('Run selection changed. Read the selected run again.');
            this.controller.edit(state => {
                if (!refresh) state.reset();
                state.load(data);
                state.editor.selection = selected;
            });
            this.message = '';
        } catch (error) {
            if (!request.signal.aborted && error.name !== 'AbortError') this.message = error.message;
        } finally {
            if (this.request === request) {
                this.request = null;
                if (!this.controller.disposed) this.render();
            }
        }
    }
    render() {
        if (!this.listening && api.addEventListener) {
            api.addEventListener('eclipse-nova.video-run', this.updated);
            api.addEventListener('eclipse-nova.video-run-selection', this.selectionChanged);
            for (const name of ['execution_success', 'execution_error', 'execution_interrupted']) api.addEventListener(name, this.ended);
            api.addEventListener('eclipse-nova.loop', this.progress); this.listening = true;
        }
        const c = this.controller, state = this.state, config = state.config;
        const content = element('div', 'en-panel-content'), bar = element('div', 'en-panel-bar');
        const read = button('Read selected run', 'Reload the selected saved prompts and clear pending edits.', () => this.read());
        read.disabled = !!this.request;
        const apply = button('Apply edits', 'Use these changes on Resume or Update selected run. Update accepts changes to the selected part.', () => c.edit(s => { s.config.enabled = !s.config.enabled; }));
        apply.setAttribute('aria-pressed', String(config.enabled));
        apply.disabled = !!this.live || !!this.request || (!state.editor.catalog && !config.enabled);
        bar.append(read, apply, button('Reset editor', 'Clear the displayed run and all pending prompt edits.', () => this.reset())); content.append(bar);
        const catalog = this.request ? null : state.editor.catalog;
        const liveLabel = this.live?.finished ? 'Last run' : 'Current run';
        const source = element('div', 'en-panel-note', this.live ? (catalog?.run ? `${liveLabel} · ${catalog.run}` : liveLabel)
            : catalog ? `Read from: ${catalog.run}` : 'Queue a new run or read a saved run here.');
        source.style.overflowWrap = 'anywhere'; content.append(source);
        if (catalog?.parts.length) {
            const label = element('div', 'en-panel-field'), select = element('select');
            select.setAttribute('aria-label', 'Render part');
            for (const p of catalog.parts) {
                const option = element('option', '', `Part ${p.part} · ${p.start.toFixed(3)}–${p.end.toFixed(3)} s`);
                option.value = p.part; select.append(option);
            }
            select.value = state.editor.part ?? 1;
            select.onchange = () => this.navigate(s => { s.editor.part = Number(select.value); });
            const navigation = element('div', 'en-panel-bar en-part-prompt-navigation');
            const previous = button('◀', 'Previous prompt', () => this.navigate(s => s.stepPart(-1)));
            const next = button('▶', 'Next prompt', () => this.navigate(s => s.stepPart(1)));
            previous.className = next.className = 'en-part-prompt-step';
            const index = catalog.parts.indexOf(state.part);
            previous.disabled = index === 0;
            next.disabled = index === catalog.parts.length - 1;
            navigation.append(select, previous, next);
            label.append(element('span', '', 'Render part'), navigation); content.append(label);
            const field = element('label', 'en-panel-field en-part-prompt-field'), text = element('textarea');
            text.setAttribute('aria-label', 'Part prompt'); text.spellcheck = false;
            text.value = config.edits[state.part.part] ?? state.part.prompt;
            text.readOnly = !!this.live;
            if (!this.live) text.oninput = () => c.edit(s => s.setText(text.value), false);
            field.append(element('span', '', this.live ? 'Queued part prompt' : 'Part prompt · full replacement'), text); content.append(field);
            const actions = element('div', 'en-panel-bar');
            actions.append(button('Reset this part', 'Restore the prompt read from this saved revision.', () => c.edit(s => { delete s.config.edits[s.part.part]; })),
                button('Clear edits', 'Discard all pending edits. Saved run files are unchanged.', () => c.edit(s => { s.config.edits = {}; s.config.enabled = false; })));
            if (!this.live) content.append(actions);
        }
        const status = element('div', 'en-panel-note'); status.setAttribute('role', 'status'); this.status = status;
        content.append(status);
        if (!this.live) content.append(element('div', 'en-panel-note', 'For a completed part, set Restart part to its number or earlier. Parts per queue = 1 lets you review the replacement. Changes apply on the next queue.'));
        c.root.replaceChildren(content); this.syncSummaries(); c.measure();
    }
    syncSummaries() {
        const count = Object.keys(this.state.config.edits).length;
        if (this.status) this.status.textContent = this.message || `${count} edited part${count === 1 ? '' : 's'} · ${this.state.config.enabled ? 'Apply on next render' : 'Edits disabled'}`;
    }
    dispose() {
        this.request?.abort(); this.request = null;
        this.live = null; this.dismissed = null; this.message = '';
        if (this.listening) {
            api.removeEventListener('eclipse-nova.video-run', this.updated);
            api.removeEventListener('eclipse-nova.video-run-selection', this.selectionChanged);
            for (const name of ['execution_success', 'execution_error', 'execution_interrupted']) api.removeEventListener(name, this.ended);
            api.removeEventListener('eclipse-nova.loop', this.progress);
        }
        this.listening = false;
    }
}

app.registerExtension({
    name: 'EclipseNova.PartPrompts',
    setup() {
        ensurePanelStyle();
        api.addEventListener('eclipse-nova.part-prompts', ({ detail }) => {
            let graph = app.rootGraph ?? app.graph, node;
            if (detail.workflow_id && graph?.id !== detail.workflow_id) return;
            for (const id of String(detail.node_id).split(':')) {
                node = graph?.getNodeById(id); graph = node?.subgraph;
            }
            controllers.get(node)?.form.receive(detail);
        });
        if (!document.getElementById('en-part-prompts-style')) {
            const style = element('style'); style.id = 'en-part-prompts-style';
            style.textContent = `
                .en-part-prompts .en-panel-content{display:flex;flex-direction:column;height:100%;min-height:0}
                .en-part-prompts .en-part-prompt-field{display:flex;flex-direction:column;flex:1;min-height:90px}
                .en-part-prompts textarea{flex:1;min-height:60px;resize:none;width:100%;box-sizing:border-box}
                .en-part-prompts .en-part-prompt-navigation{flex-wrap:nowrap}
                .en-part-prompts .en-part-prompt-navigation select{flex:1;min-width:0;min-height:28px;padding:4px 6px;font:inherit;cursor:pointer;border:1px solid var(--en-select-border);border-radius:var(--en-pill-radius);background:var(--en-select-bg);color:var(--en-select-text);color-scheme:var(--en-color-scheme)}
                .en-part-prompts .en-part-prompt-navigation select option{background:var(--en-menu-bg);color:var(--en-text)}
                .en-part-prompts .en-part-prompt-navigation .en-part-prompt-step{flex:0 0 28px;min-height:28px;padding:4px 0}
            `;
            document.head.append(style);
        }
    },
    getCustomWidgets() {
        return { [WIDGET](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: PartPromptState, Form: PartPromptForm, widgetType: WIDGET, editorKey: 'eclipsePartPrompts',
                className: 'en-part-prompts', label: 'Part Prompt Editor', fillHeight: true, minHeight: 360,
                onDispose: node => controllers.delete(node),
            });
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 400, minHeight: 430 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== NODE) return;
        for (const method of ['onConfigure', 'onAdded', 'onGraphConfigured']) {
            const original = nodeType.prototype[method];
            nodeType.prototype[method] = function (...args) {
                const result = original?.apply(this, args), controller = controllers.get(this);
                if (controller && !controller.disposed) {
                    if (method === 'onConfigure') controller.restore(controller.value());
                    controller.bindHost();
                }
                return result;
            };
        }
    },
});
