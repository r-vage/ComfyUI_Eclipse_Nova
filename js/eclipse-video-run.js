/**
 * Eclipse Nova — saved run selection, backup preview and restore.
 * SPDX-License-Identifier: Apache-2.0
 */
import { app, api } from './comfy/index.js';
import { batchedRefreshVueWidgetOptions } from './eclipse-widget-utils.js';

const NODE_NAME = 'Load Video Run [Eclipse Nova]';
const NO_SAVED_RUNS = '(no saved runs found)';
const CURRENT = 'Current run';
const controllers = new WeakMap();

function normalizeRunMode(node) {
    const widget = node.widgets?.find(w => w.name === 'run_mode');
    const values = widget?.options?.values;
    // Leave a still-running older server's schema alone until it is restarted.
    if (!Array.isArray(values) || !values.includes('Update selected run')) return;
    const oldMode = 'Replace selected part only';
    if (widget.value !== oldMode && !values.includes(oldMode)) return;
    if (widget.value === oldMode) widget.value = 'Update selected run';
    widget.options.values = values.filter(value => value !== oldMode);
    batchedRefreshVueWidgetOptions(node);
    node.setDirtyCanvas(true, true);
}

export class RunBackups {
    constructor(node) {
        this.node = node; this.request = null; this.disposed = false; this.restoring = false;
        this.updated = event => {
            if (event.detail.saved_run === this.savedRun) void this.refreshBackups(true);
        };
        api.addEventListener('eclipse-nova.video-run', this.updated);
        let lastRun = this.savedRun, lastBackup = this.widget('backup').value || CURRENT;
        const selectionChanged = () => {
            const backup = this.widget('backup').value || CURRENT;
            if (lastRun === this.savedRun && lastBackup === backup && this.savedRun !== NO_SAVED_RUNS) return;
            lastRun = this.savedRun; lastBackup = backup;
            api.dispatchEvent(new CustomEvent('eclipse-nova.video-run-selection', { detail: { loader: node } }));
        };
        const run = this.widget('saved_run'), callback = run.callback;
        run.callback = (...args) => {
            const result = callback?.apply(run, args);
            this.closeReport();
            this.widget('backup').value = CURRENT;
            selectionChanged();
            void this.refreshBackups(true); return result;
        };
        const backup = this.widget('backup'), selectBackup = backup.callback;
        backup.callback = (...args) => {
            this.closeReport();
            const result = selectBackup?.apply(backup, args);
            selectionChanged(); return result;
        };
    }
    widget(name) { return this.node.widgets.find(w => w.name === name); }
    get savedRun() { return this.widget('saved_run').value; }
    normalize() { if (this.widget('backup').value == null) this.widget('backup').value = CURRENT; }
    error(summary, error) {
        if (!this.disposed) app.extensionManager.toast.add({ severity: 'error', summary, detail: error.message });
    }
    closeReport() {
        this.reportRequest?.abort();
        this.reportDialog?.close();
    }
    async previewReport() {
        this.closeReport();
        const saved_run = this.savedRun, backup = this.widget('backup').value || CURRENT;
        if (!saved_run || saved_run === NO_SAVED_RUNS) {
            this.error('Saved run report', Error('Choose a saved run first.')); return;
        }
        const request = this.reportRequest = new AbortController();
        try {
            const response = await api.fetchApi('/eclipse-nova/video_run/report', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ saved_run, backup }), signal: request.signal,
            });
            const data = await response.json();
            if (request.signal.aborted || this.disposed || this.savedRun !== saved_run
                || (this.widget('backup').value || CURRENT) !== backup) return;
            if (!response.ok) throw Error(data.error || 'Could not read the saved run.');
            const dialog = document.createElement('dialog');
            dialog.setAttribute('aria-label', 'Saved run report');
            dialog.style.cssText = 'max-width:min(48rem,90vw);max-height:80vh;overflow:auto;background:var(--comfy-menu-bg);color:var(--fg-color);padding:1.25rem;border:1px solid var(--border-color);';
            const heading = document.createElement('h2'); heading.textContent = 'Saved run report';
            const report = document.createElement('pre'); report.textContent = data.report;
            report.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;user-select:text;';
            const close = document.createElement('button'); close.textContent = 'Close';
            close.addEventListener('click', () => dialog.close());
            dialog.addEventListener('close', () => {
                dialog.remove();
                if (this.reportDialog === dialog) this.reportDialog = null;
            }, { once: true });
            dialog.append(heading, report, close); document.body.append(dialog);
            this.reportDialog = dialog; dialog.showModal();
        } catch (error) {
            if (!request.signal.aborted) this.error('Saved run report', error);
        } finally {
            if (this.reportRequest === request) this.reportRequest = null;
        }
    }
    async refreshBackups(quiet = false) {
        this.normalize(); this.request?.abort();
        const selected = this.savedRun;
        if (!this.node.graph || !selected || selected === NO_SAVED_RUNS) return null;
        const request = this.request = new AbortController();
        try {
            const response = await api.fetchApi('/eclipse-nova/video_run/backups', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ saved_run: selected }), signal: request.signal,
            });
            const data = await response.json();
            if (!response.ok) throw Error(data.error || 'Could not read backups.');
            if (request.signal.aborted || this.disposed || this.savedRun !== selected) return null;
            const widget = this.widget('backup'), values = [CURRENT, ...data.backups.map(b => b.id)];
            widget.options.values = values.includes(widget.value) ? values : [...values, widget.value];
            batchedRefreshVueWidgetOptions(this.node); this.node.setDirtyCanvas(true, true);
            return data;
        } catch (error) {
            if (!quiet && error.name !== 'AbortError') this.error('Read backups failed', error);
            return null;
        } finally { if (this.request === request) this.request = null; }
    }
    async restore() {
        if (this.restoring || this.disposed) return;
        const selected = this.savedRun, backup = this.widget('backup').value;
        if (!backup || backup === CURRENT) {
            this.error('Restore backup', Error('Select a backup first.')); return;
        }
        this.restoring = true;
        try {
            const catalog = await this.refreshBackups();
            if (!catalog || this.savedRun !== selected || this.widget('backup').value !== backup) return;
            const response = await api.fetchApi('/eclipse-nova/video_run/restore', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ saved_run: selected, backup, revision: catalog.revision }),
            });
            const data = await response.json();
            if (!response.ok) throw Error(data.error || 'Could not restore backup.');
            if (this.disposed || this.savedRun !== selected || this.widget('backup').value !== backup) return;
            this.node.graph?.beforeChange();
            const widget = this.widget('backup'); widget.value = CURRENT; widget.callback?.(CURRENT);
            this.node.graph?.afterChange();
            await this.refreshBackups();
            api.dispatchEvent(new CustomEvent('eclipse-nova.video-run', {
                detail: { ...data, saved_run: selected, operation: 'restore' },
            }));
            app.extensionManager.toast.add({ severity: 'success', summary: 'Backup restored',
                detail: 'The selected run now uses this version. The previous current version was backed up.' });
        } catch (error) { this.error('Restore backup failed', error); }
        finally { this.restoring = false; }
    }
    dispose() {
        this.disposed = true; this.request?.abort(); this.closeReport();
        api.removeEventListener('eclipse-nova.video-run', this.updated);
    }
}

app.registerExtension({
    name: 'EclipseNova.VideoRun',
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === 'Video Run Storage [Eclipse Nova]') {
            for (const method of ['onNodeCreated', 'onConfigure', 'onAdded', 'onGraphConfigured']) {
                const original = nodeType.prototype[method];
                nodeType.prototype[method] = function (...args) {
                    const result = original?.apply(this, args);
                    normalizeRunMode(this);
                    return result;
                };
            }
            return;
        }
        if (nodeData.name !== NODE_NAME) return;
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            // A browser refresh can precede the server restart that adds backup.
            const backups = this.widgets.some(w => w.name === 'backup') ? new RunBackups(this) : null;
            if (backups) controllers.set(this, backups);
            let refreshing = false;
            const button = this.addWidget('button', 'Refresh runs', null, async () => {
                if (refreshing) return;
                refreshing = true;
                button.name = 'Refreshing runs…';
                this.setDirtyCanvas(true);
                try {
                    const response = await api.fetchApi(`/object_info/${encodeURIComponent(NODE_NAME)}`);
                    if (!response.ok) throw new Error(`Run list request failed (${response.status})`);
                    const data = (await response.json())[NODE_NAME];
                    const input = data?.input?.required?.saved_run;
                    const values = Array.isArray(input?.[0]) ? input[0] : input?.[1]?.options;
                    if (!Array.isArray(values)) throw new Error('Run list is unavailable');
                    if (!this.graph) return;
                    const widget = this.widgets.find(w => w.name === 'saved_run');
                    const wasEmpty = widget.value === NO_SAVED_RUNS;
                    // A deleted/moved selection remains explicit, never silently loads another run.
                    widget.options.values = wasEmpty || values.includes(widget.value) ? values : [...values, widget.value];
                    if (wasEmpty) {
                        widget.value = values[0];
                        widget.callback?.(widget.value);
                    }
                    batchedRefreshVueWidgetOptions(this);
                    await backups?.refreshBackups();
                } catch (error) {
                    app.extensionManager.toast.add({
                        severity: 'error', summary: 'Refresh runs failed', detail: error.message,
                    });
                } finally {
                    refreshing = false;
                    button.name = 'Refresh runs';
                    this.setDirtyCanvas(true);
                }
            }, { serialize: false });
            if (backups) this.addWidget('button', 'Preview run report', null, () => backups.previewReport(), {
                serialize: false, tooltip: 'Read the selected run or backup’s saved task, preset and model before choosing a preset on the video loader.',
            });
            if (backups) this.addWidget('button', 'Restore selected backup', null, () => backups.restore(), {
                serialize: false, tooltip: 'Make the selected backup current without generating video. The current version is backed up first. Connected prompt editors reload the restored prompts and reset pending edits.',
            });
            return result;
        };
        for (const method of ['onConfigure', 'onAdded', 'onGraphConfigured']) {
            const original = nodeType.prototype[method];
            nodeType.prototype[method] = function (...args) {
                const result = original?.apply(this, args);
                const controller = controllers.get(this);
                if (controller) { controller.normalize(); void controller.refreshBackups(true); }
                return result;
            };
        }
        const onRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function (...args) {
            controllers.get(this)?.dispose(); controllers.delete(this);
            return onRemoved?.apply(this, args);
        };
    },
});
