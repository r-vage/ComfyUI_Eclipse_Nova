/** SPDX-License-Identifier: Apache-2.0
 * One Shot Planner panel in both canvases, with explicit pool/history actions.
 */
import { app, api } from './comfy/index.js';
import { ConfigurationPanel } from './eclipse-configuration-panel.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { installSeedQueueHook } from './eclipse-panel-seed-queue.js';
import { validSeed } from './eclipse-panel-seed.js';
import { stopAutomaticQueue } from './eclipse-queue-control-utils.js';
import { NODE_ID, WIDGET_TYPE, EDITOR_KEY, ShotPlannerState } from './eclipse-shot-planner-state.js';
import { ShotPlannerForm } from './eclipse-shot-planner-form.js';

const controllers = new WeakMap();
const toast = (severity, summary, detail) => app.extensionManager.toast.add({ severity, summary, detail, life: 10000 });
class ShotPlannerPanel extends ConfigurationPanel {
    connected(name) { return this.node.inputs?.some(input => input.name === name && input.link != null) === true; }
    syncConnection(restored = false, seedConnected = false) {
        if (this.disposed || this.invalid || !this.node.graph || (app.configuringGraph && !restored)) return;
        const connected = this.connected('seed_input');
        if (!connected && this.state.config.seed.source === 'input') this.edit(state => state.setLocalSeed(true, false));
        else if (seedConnected && connected && this.state.config.seed.source === 'local') this.edit(state => state.setLocalSeed(false, true));
        else this.form.render();
    }
    async reloadFiles() {
        if (this.reloading || this.disposed) return;
        const request = this.reloading = new AbortController(); this.status = 'Reloading planner files…'; this.form.render();
        try {
            const response = await api.fetchApi('/eclipse-nova/shot_planner/pools', { cache: 'no-store', signal: request.signal });
            const data = await response.json();
            if (!response.ok || !data.success || !Array.isArray(data.expression_ids)) throw Error(data.error || 'Could not load planner files.');
            if (this.disposed || request.signal.aborted) return;
            this.expressions = ['random', 'off', ...data.expression_ids];
            this.status = `Reloaded: ${data.poses} poses, ${data.expressions} expressions.`;
            toast('success', 'Planner files reloaded', `${data.directory}: new batches use these edits; reserved batches keep their saved prompts.`);
        } catch (error) {
            if (!this.disposed && !request.signal.aborted) { this.status = error.message; toast('error', 'Planner files could not be loaded', error.message); }
        } finally {
            if (this.reloading === request) this.reloading = null;
            if (!this.disposed) this.form.render();
        }
    }
    async resetReservations() {
        if (this.resetting || this.disposed) return;
        this.resetting = true; this.form.render();
        try {
            const project = await app.extensionManager.dialog.prompt({
                title: 'Reset Shot Planner reservations',
                message: 'Enter the project name to clear ALL its reserved batches. Stop queueing first. Saved images and prompts stay intact; saved plans will no longer replay. For a connected project, enter the connected name.',
                defaultValue: this.connected('project') ? '' : this.state.config.parameters.project,
            });
            if (!project?.trim() || this.disposed) return;
            this.resetRequest = new AbortController();
            const response = await api.fetchApi('/eclipse-nova/shot_planner/reset', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ project: project.trim(), confirmation: 'reset' }), signal: this.resetRequest.signal,
            });
            const data = await response.json();
            if (this.disposed || this.resetRequest.signal.aborted) return;
            if (!response.ok || !data.success) throw Error(data.error || 'Could not reset reservations.');
            this.status = `${data.project}: cleared ${data.cleared_batches} reserved batches.`;
            toast('success', 'Reservations reset', this.status);
        } catch (error) {
            if (!this.disposed && !this.resetRequest?.signal.aborted) { this.status = error.message; toast('error', 'Reservations could not be reset', error.message); }
        } finally {
            this.resetRequest = null; this.resetting = false;
            if (!this.disposed) this.form.render();
        }
    }
    dispose() { this.reloading?.abort(); this.resetRequest?.abort(); super.dispose(); }
}

app.registerExtension({
    name: 'EclipseNova.ShotPlannerPanel',
    setup() { ensurePanelStyle(); installSeedQueueHook(api, app, controllers, { nodeId: NODE_ID, editorKey: EDITOR_KEY }); },
    getCustomWidgets() {
        return { [WIDGET_TYPE](node, name, inputData) {
            const controller = new ShotPlannerPanel(node, name, inputData[1], {
                State: ShotPlannerState, Form: ShotPlannerForm, widgetType: WIDGET_TYPE, editorKey: EDITOR_KEY,
                className: 'en-shot-planner', label: 'Character Shot Planner editor', onDispose: node => controllers.delete(node),
            });
            controllers.set(node, controller); return { widget: controller.widget, minWidth: 440 };
        } };
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (data.name !== NODE_ID) return;
        for (const method of ['onConfigure', 'onAdded', 'onGraphConfigured', 'onConnectionsChange']) {
            const original = nodeType.prototype[method];
            nodeType.prototype[method] = function (...args) {
                const result = original?.apply(this, args), controller = controllers.get(this);
                if (controller && !controller.disposed) {
                    if (method === 'onConfigure') controller.restore(controller.value());
                    controller.bindHost();
                    if (method === 'onGraphConfigured' || (method === 'onConnectionsChange' && args[0] === 1)) {
                        const seedAdded = method === 'onConnectionsChange' && args[2] === true && this.inputs?.[args[1]]?.name === 'seed_input';
                        controller.syncConnection(method === 'onGraphConfigured', seedAdded);
                    }
                }
                return result;
            };
        }
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message, ...args) {
            const result = executed?.call(this, message, ...args), controller = controllers.get(this);
            if (message?.eclipse_shot_planner_stopped?.some(Boolean)) stopAutomaticQueue();
            for (const detail of message?.eclipse_shot_planner_notice ?? []) toast('warn', 'Shot Planner', detail);
            for (const detail of message?.eclipse_shot_planner_info ?? []) toast('info', 'Shot Planner preview', detail);
            if (controller) controller.edit(state => {
                if (validSeed(message?.eclipse_seed?.[0])) state.editor.lastSeed = message.eclipse_seed[0];
                if (message?.eclipse_shot_plan?.[0]) state.editor.lastPlan = message.eclipse_shot_plan[0];
            }, false);
            return result;
        };
    },
});
