/**
 * ComfyUI Import Hub - Eclipse Edition
 *
 * Centralizes all imports from ComfyUI core via window.comfyAPI.
 * All consumer files import from this hub — when ComfyUI updates
 * their public API, only this file needs to change.
 *
 * Last Updated: April 10, 2026
 * Source: window.comfyAPI (stable public API)
 */

// ── Stable public API ───────────────────────────────────────────────────
const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;
const { ComfyWidgets } = window.comfyAPI.widgets;

export { app, api, ComfyWidgets };

// Frontend 1.53 stores live previews separately from final outputs. Retire
// them through the reactive store, including its shared blob URL ownership.
export function revokeNodePreview(node) {
    const manager = app.extensionManager;
    manager._p._s.get('nodeOutput').revokePreviewsByLocatorId(manager.workflow.nodeToNodeLocatorId(node));
}

export function hasNodePreview(node) {
    return !!app.extensionManager._p._s.get('nodeOutput').getNodePreviews(node)?.length;
}

// Custom DOM previews keep their image list locally. Clear the native renderer
// through the store so both its reactive state and app mirror stay in sync.
export function clearNodeOutputImages(node) {
    const store = app.extensionManager._p._s.get('nodeOutput');
    if (store.getNodeOutputs(node)?.images?.length) store.setNodeOutputImages(node, []);
}
