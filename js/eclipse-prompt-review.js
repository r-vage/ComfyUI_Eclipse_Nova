/** Eclipse Nova — edit incoming prompts and continue the same queue. */
import { app, api } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { element, button, ensurePanelStyle } from './eclipse-panel-controls.js';

const NODE = 'Prompt Review [Eclipse Nova]';
const WIDGET = 'ECLIPSE_NOVA_PROMPT_REVIEW';
const controllers = new WeakMap();
const panels = new Set();
const rootGraph = () => app.rootGraph ?? app.graph;

export class PromptReviewState {
    constructor(raw, _spec, editor = {}) {
        this.config = JSON.parse(typeof raw === 'string' ? raw : JSON.stringify(raw));
        this.editor = JSON.parse(JSON.stringify(editor));
        const c = this.config;
        if (c?.version !== 1 || typeof c.pause !== 'boolean' || typeof c.source !== 'string'
            || !Array.isArray(c.edits) || c.edits.some(t => typeof t !== 'string')) throw Error('Invalid prompt review configuration.');
    }
    value() { return JSON.stringify(this.config); }
    load(packet, preserveDraft = false) {
        const same = this.config.source === packet.source && this.config.edits.length === packet.texts.length;
        if (!preserveDraft || !same) this.config.edits = [...packet.texts];
        this.config.source = packet.source;
        this.editor.originals = [...packet.originals];
        this.editor.hasFirst = packet.has_first;
        if (!same || !Number.isInteger(this.editor.selected) || this.editor.selected < 0 || this.editor.selected >= packet.texts.length) this.editor.selected = 0;
    }
    get selected() { return this.editor.selected ?? 0; }
}

class PromptReviewForm {
    constructor(controller) { this.controller = controller; this.active = null; this.message = ''; this.request = null; }
    get state() { return this.controller.state; }
    receive(packet) {
        if (this.controller.disposed) return;
        if (packet.status === 'closed') {
            if (this.active?.token === packet.token) { this.active = null; this.message = 'Review finished.'; this.render(); }
            return;
        }
        if (packet.status === 'waiting' && this.active?.token === packet.token) return;
        this.active = packet.status === 'waiting' ? packet : null;
        this.message = packet.status === 'waiting' ? 'Paused · edit the prompts, then Continue.'
            : packet.status === 'continued' ? 'Continued with the reviewed prompts.' : 'Passed through unchanged.';
        this.controller.edit(s => s.load(packet, packet.status === 'waiting'));
    }
    async respond(action) {
        if (!this.active || this.request) return;
        const current = this.active;
        const request = this.request = new AbortController();
        this.message = action === 'continue' ? 'Continuing…' : 'Cancelling…'; this.render();
        try {
            const response = await api.fetchApi('/eclipse-nova/prompt-review/respond', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: request.signal,
                body: JSON.stringify({ token: current.token, prompt_id: current.prompt_id,
                    client_id: api.clientId, action, texts: [...this.state.config.edits] }),
            });
            const data = await response.json();
            if (!response.ok) throw Error(data.error || 'Could not submit this review.');
            if (this.active?.token === current.token) this.active = null;
            this.message = action === 'continue' ? 'Continued with the reviewed prompts.' : 'Run cancelled.';
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
        const pause = button('⏸ Pause', 'Enable before queueing to review prompts here. Off passes incoming text through unchanged.', () => { this.message = ''; c.edit(s => { s.config.pause = !s.config.pause; }); });
        pause.setAttribute('aria-pressed', String(config.pause)); pause.disabled = !!this.active || !!this.request;
        const play = button('▶ Continue', 'Send these edits downstream and continue this run. The prompt source is not rerun.', () => this.respond('continue'));
        play.disabled = !this.active || !!this.request;
        const cancel = button('■ Cancel run', 'Cancel the waiting run. Nothing is sent downstream.', () => this.respond('cancel'));
        cancel.disabled = !this.active || !!this.request;
        bar.append(pause, play, cancel); content.append(bar);
        const texts = config.edits;
        if (texts.length) {
            const label = element('div', 'en-panel-field'), select = element('select');
            select.setAttribute('aria-label', 'Prompt to review');
            texts.forEach((_text, index) => {
                const name = state.editor.hasFirst ? index === 0 ? 'First prompt' : `Prompt ${index + 1}` : `Prompt ${index + 1}`;
                const option = element('option', '', name); option.value = index; select.append(option);
            });
            select.value = state.selected;
            select.onchange = () => c.edit(s => { s.editor.selected = Number(select.value); });
            const navigation = element('div', 'en-panel-bar en-review-navigation');
            const previous = button('◀', 'Previous prompt', () => c.edit(s => { s.editor.selected = Math.max(0, s.selected - 1); }));
            const next = button('▶', 'Next prompt', () => c.edit(s => { s.editor.selected = Math.min(s.config.edits.length - 1, s.selected + 1); }));
            previous.className = next.className = 'en-review-step';
            previous.disabled = state.selected === 0;
            next.disabled = state.selected === texts.length - 1;
            navigation.append(select, previous, next);
            label.append(element('span', '', `${texts.length} prompt${texts.length === 1 ? '' : 's'}`), navigation); content.append(label);
        }
        const field = element('label', 'en-panel-field en-review-text'), text = element('textarea');
        text.setAttribute('aria-label', 'Prompt text'); text.spellcheck = false;
        text.value = texts[state.selected] ?? ''; text.readOnly = !this.active || !!this.request;
        text.placeholder = 'Incoming prompts appear here when the node runs.';
        text.oninput = () => c.edit(s => { s.config.edits[s.selected] = text.value; }, false);
        field.append(text); content.append(field);
        const actions = element('div', 'en-panel-bar');
        const reset = button('Reset this prompt', 'Restore the text received from the source.', () => c.edit(s => { s.config.edits[s.selected] = s.editor.originals[s.selected]; }));
        reset.disabled = !this.active || !!this.request;
        actions.append(reset, button('Refresh status', 'Reconnect to a waiting review after reloading the workflow.', () => syncPending())); content.append(actions);
        this.status = element('div', 'en-panel-note'); this.status.setAttribute('role', 'status'); content.append(this.status);
        for (const control of content.querySelectorAll('button:not(.en-review-step)')) control.setAttribute('aria-label', control.textContent);
        c.root.replaceChildren(content); this.syncSummaries(); c.measure();
    }
    syncSummaries() {
        if (this.status) this.status.textContent = this.message || (this.state.config.pause ? 'Will pause when prompts arrive.' : 'Pause off · input passes through unchanged.');
    }
    dispose() { this.request?.abort(); this.request = null; }
}

function receive(packet) {
    let graph = rootGraph(), node;
    if (packet.workflow_id && graph?.id !== packet.workflow_id) return;
    for (const id of String(packet.node_id ?? '').split(':')) {
        node = graph?.getNodeById(id); graph = node?.subgraph;
    }
    controllers.get(node)?.form.receive(packet);
}

let pendingRequest;
async function syncPending() {
    if (!api.clientId) return;
    pendingRequest?.abort();
    const request = pendingRequest = new AbortController();
    const workflow = rootGraph()?.id ?? null;
    const waiting = [...panels].filter(c => c.form.active?.workflow_id === workflow)
        .map(c => [c, c.form.active]);
    try {
        const response = await api.fetchApi('/eclipse-nova/prompt-review/pending', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: request.signal,
            body: JSON.stringify({ client_id: api.clientId, workflow_id: workflow }),
        });
        if (!response.ok) throw Error('Could not refresh the waiting review.');
        const { reviews } = await response.json();
        if (request.signal.aborted) return;
        for (const packet of reviews) receive(packet);
        for (const [controller, active] of waiting) {
            if (!controller.disposed && controller.form.active === active
                && !reviews.some(p => p.token === active.token)) {
                controller.form.receive({ ...active, status: 'closed' });
            }
        }
    } catch (error) {
        if (error.name !== 'AbortError') app.extensionManager.toast.add({ severity: 'error', summary: 'Prompt Review', detail: 'Could not refresh the waiting review.' });
    } finally { if (pendingRequest === request) pendingRequest = null; }
}

app.registerExtension({
    name: 'EclipseNova.PromptReview',
    setup() {
        ensurePanelStyle();
        if (!document.getElementById('en-prompt-review-style')) {
            const style = element('style'); style.id = 'en-prompt-review-style';
            style.textContent = '.en-prompt-review .en-panel-content{display:flex;flex-direction:column;height:100%;min-height:0}.en-prompt-review .en-review-text{display:flex;flex-direction:column;flex:1;min-height:90px}.en-prompt-review textarea{flex:1;min-height:60px;resize:none;width:100%;box-sizing:border-box}.en-prompt-review .en-review-navigation{flex-wrap:nowrap}.en-prompt-review .en-review-navigation select{flex:1;min-width:0;min-height:28px;padding:4px 6px;font:inherit;cursor:pointer;border:1px solid var(--en-select-border);border-radius:var(--en-pill-radius);background:var(--en-select-bg);color:var(--en-select-text);color-scheme:var(--en-color-scheme)}.en-prompt-review .en-review-navigation select option{background:var(--en-menu-bg);color:var(--en-text)}.en-prompt-review .en-review-navigation .en-review-step{flex:0 0 28px;min-height:28px;padding:4px 0}';
            document.head.append(style);
        }
        api.addEventListener('eclipse-nova.prompt-review', event => receive(event.detail));
        api.addEventListener('reconnected', syncPending);
    },
    getCustomWidgets() {
        return { [WIDGET](node, name, inputData) {
            const controller = new ConfigurationPanel(node, name, inputData[1], {
                State: PromptReviewState, Form: PromptReviewForm, widgetType: WIDGET, editorKey: 'eclipsePromptReview',
                className: 'en-prompt-review', label: 'Prompt Review', fillHeight: true, minHeight: 330,
                onDispose: node => { panels.delete(controllers.get(node)); controllers.delete(node); },
            });
            controllers.set(node, controller); panels.add(controller); return { widget: controller.widget, minWidth: 400, minHeight: 410 };
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
                    if (method === 'onGraphConfigured') queueMicrotask(syncPending);
                }
                return result;
            };
        }
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (output) {
            const result = executed?.apply(this, arguments);
            const packet = output?.prompt_review?.[0];
            if (packet) controllers.get(this)?.form.receive(packet);
            return result;
        };
    },
});
