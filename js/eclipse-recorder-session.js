/** SPDX-License-Identifier: Apache-2.0
 * Explicit recorder actions; status polling exists only while a capture is active.
 */
import { app, api } from './comfy/index.js';
import { executionTarget, queueEntries } from './eclipse-execution-scope.js';

const NODE_ID = 'System Audio Recorder [Eclipse Nova]';
const ENDPOINT = '/eclipse-nova/system_audio';
const CAPTURE = new Set(['starting', 'recording', 'stopping', 'captured']);
const RETAINED = new Set(['ready', 'processing_error']);
const sessions = new Map(), prompts = new Map(), earlyFailures = new Set();

async function request(path, body, signal) {
    const response = await api.fetchApi(`${ENDPOINT}/${path}`, body === undefined ? { cache: 'no-store', signal } : {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal,
    });
    const data = await response.json();
    if (!response.ok || data.success === false) {
        const error = Error(data.error || `Recorder request failed (${response.status}).`); error.status = response.status; throw error;
    }
    return data;
}
function forget(token, session) {
    if (sessions.get(token) === session) sessions.delete(token);
    for (const [id, owners] of prompts) { owners.delete(session); if (!owners.size) prompts.delete(id); }
}

export function installRecorderQueueHooks() {
    const queue = api.queuePrompt;
    api.queuePrompt = async function (number, prompt, options) {
        const response = await queue.apply(this, arguments);
        if (response?.prompt_id == null) return response;
        const id = String(response.prompt_id), owners = new Set();
        for (const [, node] of queueEntries(prompt, options, node => node.class_type === NODE_ID)) {
            let config; try { config = JSON.parse(node.inputs.configuration); } catch { continue; }
            const session = sessions.get(config.recording_token); if (session) owners.add(session);
        }
        if (owners.size) {
            prompts.set(id, owners);
            if (earlyFailures.delete(id)) for (const session of owners) void session.abort('Workflow execution failed before recording completed.');
        }
        return response;
    };
    const failure = ({ detail } = {}) => {
        if (detail?.prompt_id == null) return;
        const id = String(detail.prompt_id), owners = prompts.get(id);
        if (owners) { for (const session of owners) void session.abort('Workflow execution was interrupted.'); prompts.delete(id); }
        else { earlyFailures.add(id); while (earlyFailures.size > 32) earlyFailures.delete(earlyFailures.values().next().value); }
    };
    api.addEventListener('execution_error', failure); api.addEventListener('execution_interrupted', failure);
    api.addEventListener('execution_success', ({ detail } = {}) => { prompts.delete(String(detail?.prompt_id)); });
}

export class RecorderSession {
    constructor(controller) { this.controller = controller; this.state = 'idle'; this.elapsed = 0; this.error = ''; this.generation = 0; }
    get token() { return this.controller.state.config.recording_token; }
    get params() { return this.controller.state.config.parameters; }
    get active() { return CAPTURE.has(this.state) || this.state === 'restoring'; }
    get ready() { return !!this.token && RETAINED.has(this.state); }
    get dead() { return this.disposed || this.controller.disposed; }
    ownerId(requireEnabled = false) { return executionTarget(app.rootGraph ?? app.graph, this.controller.node, { requireEnabled }); }
    sync() { if (!this.dead) { this.controller.form.syncRecorder(); this.controller.measure(); } }
    setToken(value) {
        if (this.dead) return;
        this.controller.state.config.recording_token = value;
        this.controller.raw = this.controller.state.value(); this.controller.node.setDirtyCanvas(true, true);
    }
    payload(token = this.token) {
        const p = this.params;
        return { node_id: this.owner, ...(token ? { token } : {}), filename_prefix: p.filename_prefix,
            format: p.format, mp3_bitrate: p.mp3_bitrate, strip_start_silence: p.strip_start_silence,
            silence_threshold_db: p.silence_threshold_db };
    }
    stopPolling() { clearTimeout(this.timer); this.timer = null; this.generation++; }
    apply(remote) {
        this.state = remote.state ?? 'idle'; this.elapsed = remote.elapsed ?? 0; this.error = remote.error ?? '';
        if (['aborted', 'released', 'error'].includes(this.state)) { forget(this.token, this); this.setToken(''); }
        if (!this.active) this.stopPolling(); this.sync();
    }
    async poll() {
        const generation = this.generation, token = this.token;
        if (this.dead || !token) return;
        try {
            const remote = await request('status', { node_id: this.owner, token });
            if (this.dead || generation !== this.generation || token !== this.token) return;
            this.apply(remote);
            if (this.active) this.timer = setTimeout(() => void this.poll(), 500);
        } catch (error) {
            if (this.dead || generation !== this.generation || token !== this.token) return;
            this.error = error.message;
            if ([400, 403, 404].includes(error.status)) {
                this.stopPolling(); this.state = 'error'; forget(token, this); this.setToken('');
            } else {
                // Keep the capture and its Stop control reachable after a transient
                // status failure. A missing/foreign session is handled above.
                if (this.state === 'restoring') this.state = 'recording';
                this.timer = setTimeout(() => void this.poll(), 1000);
            }
            this.sync();
        }
    }
    scheduleRestore() {
        cancelAnimationFrame(this.restoreFrame);
        this.restoreFrame = requestAnimationFrame(() => { this.restoreFrame = null; this.restore(); });
    }
    restore() {
        if (this.dead || this.busy || this.controller.invalid) return;
        const token = this.token;
        if (token && this.claimed === token && sessions.get(token) === this) { this.sync(); return; }
        this.stopPolling();
        if (this.claimed) forget(this.claimed, this);
        this.claimed = token;
        if (!token) { this.state = 'idle'; this.error = ''; this.sync(); return; }
        try {
            this.owner = this.ownerId();
            const previous = sessions.get(token);
            if (previous && previous !== this && previous.owner !== this.owner) {
                this.setToken(''); this.state = 'idle'; this.error = 'This recording belongs to another node. Start a new capture.'; this.sync(); return;
            }
            previous?.stopPolling(); sessions.set(token, this); this.state = 'restoring'; this.sync(); void this.poll();
        } catch (error) { this.error = error.message; this.state = 'idle'; this.sync(); }
    }
    async openDevices(trigger, menu) {
        if (this.dead || this.active || this.busy) return;
        if (menu.trigger === trigger) { menu.close(true); return; }
        this.deviceRequest?.abort(); this.deviceRequest = new AbortController(); const requestId = this.deviceRequest;
        trigger.setAttribute('aria-busy', 'true');
        try {
            const data = await request('devices', undefined, requestId.signal);
            if (this.dead || requestId !== this.deviceRequest || !trigger.isConnected || this.active) return;
            const devices = data.devices ?? [];
            if (!devices.length) throw Error('No system output devices were detected.');
            const labels = new Map(devices.map(device => {
                const name = device.id === 'default' ? 'Default' : String(device.name || 'Output device');
                const duplicate = device.id !== 'default' && devices.filter(item => item.id !== 'default' && item.name === device.name).length > 1;
                return [device.id, duplicate ? `${name} (${String(device.id).slice(0, 6)})` : name];
            }));
            menu.open(trigger, 'Output device', this.params.output_device, devices.map(device => device.id), id => {
                this.controller.edit(state => {
                    state.config.parameters.output_device = id;
                    state.editor.deviceLabel = labels.get(id);
                });
            }, id => labels.get(id));
            this.error = ''; this.sync();
        } catch (error) { if (!this.dead && error.name !== 'AbortError') { this.error = error.message; this.sync(); } }
        finally { trigger.removeAttribute('aria-busy'); }
    }
    async start() {
        if (this.dead || this.busy || this.active) return;
        this.busy = true; this.error = ''; this.state = 'starting'; this.sync(); let token = '', owner;
        try {
            owner = this.owner = this.ownerId(true);
            if (this.token) { const previous = this.token; await request('release', { node_id: owner, token: previous }); forget(previous, this); this.setToken(''); }
            if (this.dead) return;
            const remote = await request('start', { ...this.payload(''), output_device: this.params.output_device });
            token = String(remote.token ?? ''); if (!token) throw Error('Recorder start did not return a session token.');
            if (this.dead) { await request('release', { node_id: owner, token }); return; }
            this.setToken(token); this.claimed = token; sessions.set(token, this); this.apply(remote); void this.poll();
            const submitted = await app.queuePrompt(0);
            if (!submitted) throw Error('ComfyUI did not accept the workflow submission.');
        } catch (error) {
            this.stopPolling();
            if (token) { await request('abort', { node_id: owner, token }).catch(() => {}); forget(token, this); this.setToken(''); }
            if (!this.dead) { this.state = this.token ? 'ready' : 'idle'; this.error = error.message; }
        } finally { this.busy = false; this.sync(); }
    }
    async stop() {
        if (this.dead || this.busy || !this.token || !this.active) return;
        this.busy = true; this.error = ''; this.state = 'stopping'; this.stopPolling(); this.sync();
        try { const remote = await request('stop', this.payload()); if (!this.dead) this.apply(remote); }
        catch (error) {
            if (!this.dead) { this.state = 'restoring'; this.error = error.message; void this.poll(); }
        }
        finally { this.busy = false; this.sync(); }
    }
    async update() {
        if (this.dead || this.busy || !this.ready) return;
        this.busy = true; this.error = ''; this.sync();
        try {
            const remote = await request('reprocess', this.payload());
            if (this.dead) return;
            this.apply(remote);
            if (!await app.queuePrompt(0)) throw Error('ComfyUI did not accept the workflow submission.');
        } catch (error) { if (!this.dead) this.error = error.message; }
        finally { this.busy = false; this.sync(); }
    }
    async abort(message) {
        if (this.dead || !this.active || !this.token) return;
        const token = this.token; this.stopPolling(); forget(token, this); this.setToken(''); this.state = 'idle'; this.error = message; this.sync();
        await request('abort', { node_id: this.owner, token }).catch(() => {});
    }
    dispose() {
        if (this.disposed) return;
        const token = this.token, owner = this.owner;
        this.disposed = true; this.stopPolling(); cancelAnimationFrame(this.restoreFrame); this.deviceRequest?.abort(); forget(token, this);
        // A workflow reload can immediately recreate the same owner. Only release
        // when no replacement has claimed its retained source after mounting.
        if (token && owner) requestAnimationFrame(() => requestAnimationFrame(() => {
            if (!sessions.has(token)) void request('release', { node_id: owner, token }).catch(() => {});
        }));
    }
}
