/**
 * Surface Eclipse execution/validation errors without changing queue behavior.
 * SPDX-License-Identifier: Apache-2.0
 */
import { app, api } from './comfy/index.js';
import { showEclipseToast } from './eclipse-notifications.js';

const ownedNodes = new Map();
let installed = false;

function reportValidation(response, prompt) {
    for (const [id, failure] of Object.entries(response?.node_errors ?? {})) {
        const type = failure?.class_type ?? prompt?.[id]?.class_type;
        if (!ownedNodes.has(type)) continue;
        const errors = Array.isArray(failure?.errors) ? failure.errors : [];
        const detail = errors.map(error => [error?.message, error?.details]
            .filter(value => typeof value === 'string' && value).join(': ')).filter(Boolean).join('\n');
        showEclipseToast(`${ownedNodes.get(type)} · ${id}`, detail || 'Input validation failed. See the node error details.');
    }
}

app.registerExtension({
    name: 'EclipseNova.ErrorNotifications',
    beforeRegisterNodeDef(_nodeType, nodeData) {
        // Nova owns a distinct suffix; companion packs retain their own IDs.
        if (nodeData.name?.endsWith('[Eclipse Nova]')) {
            ownedNodes.set(nodeData.name, nodeData.display_name || nodeData.name);
        }
    },
    setup() {
        if (installed) return;
        installed = true;
        api.addEventListener('execution_error', ({ detail }) => {
            if (!ownedNodes.has(detail?.node_type)) return;
            showEclipseToast(`${ownedNodes.get(detail.node_type)} · ${detail.node_id}`,
                detail.exception_message || detail.exception_type || 'Execution failed. See the node error details.');
        });
        const originalQueue = api.queuePrompt;
        api.queuePrompt = async function (number, data, ...options) {
            try {
                const response = await originalQueue.call(this, number, data, ...options);
                reportValidation(response, data?.output);
                return response;
            } catch (error) {
                reportValidation(error?.response ?? error, data?.output);
                // Preserve the exact rejection, native error details, node
                // highlighting and all existing stop/cleanup behavior.
                throw error;
            }
        };
    },
});
