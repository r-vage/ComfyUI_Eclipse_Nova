/** Native run-to-node action beside the existing normal-queue Stop toggle. */
import { app } from './comfy/index.js';
import { button, element } from './eclipse-panel-controls.js';
import { executionTarget } from './eclipse-execution-scope.js';

export function runActions(controller, {
    stop = false, beforeRun, runLocally, stopConfig = state => state.config,
    playText = '▶', playLabel = 'Run to this node',
    playTooltip = 'Run this node and its required inputs once. Downstream nodes stay idle; Stop does not need to be enabled.',
} = {}) {
    const actions = element('div', 'en-panel-run-actions');
    actions.setAttribute('role', 'group'); actions.setAttribute('aria-label', 'Execution');
    const play = button(playText, playLabel, async () => {
        if (controller.disposed || controller.invalid || controller.playSubmitting) return;
        try {
            // A preview with no connected dependencies can finish in the browser.
            if (runLocally?.() === true) return;
            if (app.processingQueue) throw Error('Another prompt is being submitted. Try again when it has been queued.');
            const id = executionTarget(app.rootGraph ?? app.graph, controller.node);
            controller.playSubmitting = true;
            beforeRun?.(); sync();
            // One native partial run, with normal queue hooks and cache behavior.
            // The existing Stop configuration is deliberately left unchanged.
            await app.queuePrompt(0, 1, { queueNodeIds: [id] });
        } catch (error) {
            app.extensionManager.toast.add({ severity: 'error', summary: 'Could not run to this node', detail: error.message });
        } finally { controller.playSubmitting = false; sync(); }
    });
    play.dataset.enRun = '';
    play.title = playTooltip;
    play.disabled = controller.playSubmitting === true;
    actions.append(play);
    if (stop) {
        const toggle = button('■', 'Stop', () => controller.edit(state => { const config = stopConfig(state); config.stop = !config.stop; }));
        toggle.setAttribute('aria-pressed', String(stopConfig(controller.state).stop === true));
        toggle.title = 'Stop normal queues here after a changed execution. Queue again unchanged to continue from the cached result. Play already ends here without enabling Stop.';
        actions.append(toggle);
    }
    function sync() {
        if (controller.disposed) return;
        for (const current of controller.root.querySelectorAll('[data-en-run]')) {
            current.disabled = controller.playSubmitting === true;
            current.setAttribute('aria-busy', String(controller.playSubmitting === true));
        }
    }
    return actions;
}
