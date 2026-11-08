/**
 * Eclipse Nova — saved video run list refresh.
 * SPDX-License-Identifier: Apache-2.0
 */
import { app, api } from './comfy/index.js';
import { batchedRefreshVueWidgetOptions } from './eclipse-widget-utils.js';

const NODE_NAME = 'Load Video Run [Eclipse Nova]';
const NO_SAVED_RUNS = '(no saved runs found)';

app.registerExtension({
    name: 'EclipseNova.VideoRun',
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) return;
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
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
            return result;
        };
    },
});
