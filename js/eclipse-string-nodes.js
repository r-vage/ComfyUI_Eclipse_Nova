/** Native String Dual textarea styling; panel nodes own their text controls. */
import { app } from './comfy/index.js';
import { onVueModeChange } from './eclipse-widget-utils.js';

const NODE_ID = 'String Dual [Eclipse Nova]';
const trackedNodes = new Set();
const trackedNodesById = new Map();
const trackedNodeIds = new WeakMap();
const pendingTrackedNodeRefreshes = new WeakSet();
const nodeElementCache = new WeakMap();
let textareaObserver = null;
let syncPending = false;

(function injectCSS() {
    if (document.getElementById('eclipse-textarea-styles')) return;
    const s = document.createElement('style');
    s.id = 'eclipse-textarea-styles';
    s.textContent = `
textarea.eclipse-textarea {
    font-family: monospace;
    font-size: 12px;
    padding: 6px;
    border-radius: 4px;
    overflow-y: auto;
}`;
    document.head.appendChild(s);
})();

function addTextareasFromElement(element, textareas) {
    if (!element) return;
    if (element.tagName === 'TEXTAREA') textareas.add(element);
    for (const textarea of element.querySelectorAll?.('textarea') || []) {
        textareas.add(textarea);
    }
}

function getNodeTextareas(node) {
    const textareas = new Set();
    for (const widget of node.widgets || []) {
        addTextareasFromElement(widget.element, textareas);
    }

    let element = nodeElementCache.get(node);
    const nodeId = getAssignedNodeId(node);
    if ((!element || element.isConnected === false) && nodeId !== null) {
        const escapedId = globalThis.CSS?.escape
            ? CSS.escape(nodeId)
            : nodeId.replace(/["\\]/g, '\\$&');
        element = document.querySelector?.(
            `.lg-node[data-node-id="${escapedId}"]`
        );
        if (element) nodeElementCache.set(node, element);
    }
    addTextareasFromElement(element, textareas);
    return textareas;
}

function getAssignedNodeId(node) {
    return node.id == null || node.id === -1 ? null : String(node.id);
}

function indexTrackedNode(node) {
    const previousId = trackedNodeIds.get(node) ?? null;
    const nodeId = getAssignedNodeId(node);
    if (previousId !== null && previousId !== nodeId && trackedNodesById.get(previousId) === node) {
        trackedNodesById.delete(previousId);
    }
    if (nodeId === null) {
        trackedNodeIds.delete(node);
        return false;
    }
    trackedNodeIds.set(node, nodeId);
    trackedNodesById.set(nodeId, node);
    return true;
}

function trackNode(node) {
    trackedNodes.add(node);
    return indexTrackedNode(node);
}

function scheduleTrackedNodeRefresh(node) {
    if (app.configuringGraph || pendingTrackedNodeRefreshes.has(node)) return;
    pendingTrackedNodeRefreshes.add(node);
    requestAnimationFrame(() => {
        pendingTrackedNodeRefreshes.delete(node);
        if (!trackedNodes.has(node)) return;
        indexTrackedNode(node);
        applyTextareaAppearance(node);
    });
}

function untrackNode(node) {
    trackedNodes.delete(node);
    nodeElementCache.delete(node);
    const nodeId = trackedNodeIds.get(node) ?? null;
    trackedNodeIds.delete(node);
    if (nodeId !== null && trackedNodesById.get(nodeId) === node) {
        trackedNodesById.delete(nodeId);
    }
}

function applyTextareaAppearance(node) {
    for (const textarea of getNodeTextareas(node)) {
        textarea.classList.add('eclipse-textarea');
    }
}

function syncTrackedNodes() {
    syncPending = false;
    trackedNodesById.clear();
    for (const node of trackedNodes) indexTrackedNode(node);
    for (const element of document.querySelectorAll?.('.lg-node[data-node-id]') || []) {
        const node = trackedNodesById.get(element.getAttribute?.('data-node-id'));
        if (node) nodeElementCache.set(node, element);
    }
    for (const node of trackedNodes) {
        applyTextareaAppearance(node);
    }
}

function scheduleTrackedNodeSync() {
    if (syncPending) return;
    syncPending = true;
    queueMicrotask(syncTrackedNodes);
}

function syncAddedTextareaElement(element) {
    const nodeElement = element.matches?.('.lg-node[data-node-id]') ||
        element.getAttribute?.('data-node-id') != null
        ? element
        : element.closest?.('.lg-node[data-node-id]');
    if (!nodeElement) return;
    const node = trackedNodesById.get(nodeElement.getAttribute?.('data-node-id'));
    if (!node) return;
    nodeElementCache.set(node, nodeElement);
    applyTextareaAppearance(node);
}

function syncAddedTextareas(records) {
    for (const record of records) {
        for (const addedNode of record.addedNodes || []) {
            if (addedNode.tagName === 'TEXTAREA' ||
                addedNode.matches?.('.lg-node[data-node-id]') ||
                addedNode.getAttribute?.('data-node-id') != null ||
                addedNode.querySelector?.('textarea')) {
                syncAddedTextareaElement(addedNode);
            }
            for (const element of addedNode.querySelectorAll?.(
                '.lg-node[data-node-id], textarea'
            ) || []) {
                syncAddedTextareaElement(element);
            }
        }
    }
}

function startTextareaObserver() {
    if (textareaObserver || typeof MutationObserver !== 'function') return;
    const observerTarget = document.documentElement;
    if (!observerTarget) return;
    textareaObserver = new MutationObserver(syncAddedTextareas);
    textareaObserver.observe(observerTarget, { childList: true, subtree: true });
}

app.registerExtension({
    name: 'EclipseNova.StringNodes',
    setup() {
        startTextareaObserver();
        onVueModeChange(scheduleTrackedNodeSync);
    },
    async beforeRegisterNodeDef(nodeType, nodeData, _app) {
        if (nodeData.name !== NODE_ID) return;
        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const ret = origOnNodeCreated?.apply(this, arguments);
            const indexed = trackNode(this);
            if (!app.configuringGraph) {
                applyTextareaAppearance(this);
                if (!indexed) scheduleTrackedNodeRefresh(this);
            }
            return ret;
        };

        const origOnRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            untrackNode(this);
            return origOnRemoved?.apply(this, arguments);
        };

    },
    nodeCreated(node) {
        if (node.type !== NODE_ID) return;
        const indexed = trackNode(node);
        if (!app.configuringGraph) {
            applyTextareaAppearance(node);
            if (!indexed) scheduleTrackedNodeRefresh(node);
        }
    },
    loadedGraphNode(node) {
        if (node.type !== NODE_ID) return;
        const indexed = trackNode(node);
        if (!app.configuringGraph) {
            applyTextareaAppearance(node);
            if (!indexed) scheduleTrackedNodeRefresh(node);
        }
    },
    async afterConfigureGraph() {
        scheduleTrackedNodeSync();
    },
});
