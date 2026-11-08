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

export class PartPromptState {
    constructor(raw, _spec, editor = {}) {
        this.config = typeof raw === 'string' ? JSON.parse(raw) : JSON.parse(JSON.stringify(raw));
        // ComfyUI restores node properties through Vue proxies in both renderers.
        this.editor = JSON.parse(JSON.stringify(editor));
        const c = this.config;
        if (c?.version !== 1 || typeof c.enabled !== 'boolean' || typeof c.source !== 'string'
            || !c.edits || typeof c.edits !== 'object' || Array.isArray(c.edits)) throw Error('Invalid part prompt configuration.');
    }
    value() { return JSON.stringify(this.config); }
    load(catalog) {
        if (this.config.source !== catalog.source && Object.keys(this.config.edits).length) {
            throw Error('Clear edits before reading a different run. Your current edits are still kept.');
        }
        this.config.source = catalog.source;
        this.editor.catalog = catalog;
        if (!catalog.parts.some(p => p.part === this.editor.part)) this.editor.part = 1;
        // A saved edited revision already contains these replacements.
        for (const p of catalog.parts) if (this.config.edits[p.part] === p.prompt) delete this.config.edits[p.part];
    }
    get part() { return this.editor.catalog?.parts.find(p => p.part === (this.editor.part ?? 1)); }
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

export function selectedRun(node) {
    let source = upstream(node, node.inputs?.findIndex(i => i.name === 'run_path'));
    const visited = new Set();
    while (source?.node && !visited.has(source.node)) {
        const current = source.node; visited.add(current);
        if (current.type === 'Load Video Run [Eclipse Nova]' && source.slot === 7) {
            return current.widgets.find(w => w.name === 'saved_run')?.value;
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

class PartPromptForm {
    constructor(controller) { this.controller = controller; this.request = null; this.message = ''; }
    get state() { return this.controller.state; }
    async read() {
        const selected = selectedRun(this.controller.node);
        if (!selected) { this.message = 'Connect Load Video Run → run_path directly or through Get/Set.'; this.render(); return; }
        this.request?.abort();
        const request = this.request = new AbortController();
        this.message = 'Reading saved prompts…'; this.render();
        try {
            const response = await api.fetchApi('/eclipse-nova/video_run/prompts', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ saved_run: selected }), signal: request.signal,
            });
            const data = await response.json();
            if (!response.ok) throw Error(data.error || 'Could not read saved prompts.');
            if (request.signal.aborted || this.controller.disposed) return;
            if (selectedRun(this.controller.node) !== selected) throw Error('Run selection changed. Read the selected run again.');
            this.controller.edit(state => state.load(data));
            this.message = '';
        } catch (error) {
            if (error.name !== 'AbortError') this.message = error.message;
        } finally {
            if (this.request === request) this.request = null;
            if (!this.controller.disposed) this.render();
        }
    }
    render() {
        const c = this.controller, state = this.state, config = state.config;
        const content = element('div', 'en-panel-content'), bar = element('div', 'en-panel-bar');
        const read = button('Read selected run', 'Read prompts and timing only. No models or media arrays are loaded.', () => this.read());
        read.disabled = !!this.request;
        const apply = button('Apply edits', 'Use these replacements on Resume. New run and Load saved run ignore this editor.', () => c.edit(s => { s.config.enabled = !s.config.enabled; }));
        apply.setAttribute('aria-pressed', String(config.enabled));
        bar.append(read, apply); content.append(bar);
        const catalog = state.editor.catalog;
        const source = element('div', 'en-panel-note', catalog ? `Read from: ${catalog.run}` : 'Select a saved run in Load Video Run, then read its prompts here.');
        source.style.overflowWrap = 'anywhere'; content.append(source);
        if (catalog) {
            const label = element('label', 'en-panel-field'), select = element('select');
            select.setAttribute('aria-label', 'Render part');
            for (const p of catalog.parts) {
                const option = element('option', '', `Part ${p.part} · ${p.start.toFixed(3)}–${p.end.toFixed(3)} s`);
                option.value = p.part; select.append(option);
            }
            select.value = state.editor.part ?? 1;
            select.onchange = () => c.edit(s => { s.editor.part = Number(select.value); });
            label.append(element('span', '', 'Render part'), select); content.append(label);
            const field = element('label', 'en-panel-field en-part-prompt-field'), text = element('textarea');
            text.setAttribute('aria-label', 'Part prompt'); text.spellcheck = false;
            text.value = config.edits[state.part.part] ?? state.part.prompt;
            text.oninput = () => c.edit(s => s.setText(text.value), false);
            field.append(element('span', '', 'Part prompt · full replacement'), text); content.append(field);
            const actions = element('div', 'en-panel-bar');
            actions.append(button('Reset this part', 'Restore the prompt read from this saved revision.', () => c.edit(s => { delete s.config.edits[s.part.part]; })),
                button('Clear edits', 'Discard all pending edits. Saved run files are unchanged.', () => c.edit(s => { s.config.edits = {}; s.config.enabled = false; })));
            content.append(actions);
        }
        const status = element('div', 'en-panel-note'); status.setAttribute('role', 'status'); this.status = status;
        content.append(status, element('div', 'en-panel-note', 'For a completed part, set Restart part to its number or earlier. Parts per queue = 1 lets you review the replacement. Changes apply on the next queue.'));
        c.root.replaceChildren(content); this.syncSummaries(); c.measure();
    }
    syncSummaries() {
        const count = Object.keys(this.state.config.edits).length;
        if (this.status) this.status.textContent = this.message || `${count} edited part${count === 1 ? '' : 's'} · ${this.state.config.enabled ? 'Apply on Resume' : 'Edits disabled'}`;
    }
    dispose() { this.request?.abort(); this.request = null; }
}

app.registerExtension({
    name: 'EclipseNova.PartPrompts',
    setup() {
        ensurePanelStyle();
        if (!document.getElementById('en-part-prompts-style')) {
            const style = element('style'); style.id = 'en-part-prompts-style';
            style.textContent = '.en-part-prompts .en-panel-content{display:flex;flex-direction:column;height:100%;min-height:0}.en-part-prompts .en-part-prompt-field{display:flex;flex-direction:column;flex:1;min-height:90px}.en-part-prompts textarea{flex:1;min-height:60px;resize:none;width:100%;box-sizing:border-box}.en-part-prompts select{width:100%}';
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
