/**
 * eclipse-conversion-nodes.js — primitive conversion output typing
 *
 * Copyright (c) 2026 r-vage. MIT License.
 */
import {
    app
} from './comfy/index.js';
const CONVERSION_NODES = {
    'Convert Primitive [Eclipse Nova]': {
        widgetName: 'convert_to',
        typeMap: {
            STRING: {
                type: 'STRING',
                name: 'STRING'
            },
            INT: {
                type: 'INT',
                name: 'INT'
            },
            FLOAT: {
                type: 'FLOAT',
                name: 'FLOAT'
            },
            BOOLEAN: {
                type: 'BOOLEAN',
                name: 'BOOLEAN'
            },
            COMBO: {
                type: 'COMBO',
                name: 'COMBO'
            },
        },
        defaultType: '*',
    },
};
const updatingNodes = new WeakSet();

function updateOutputTypeFromWidget(node, config) {
    if (updatingNodes.has(node)) return;
    const comboWidget = node.widgets?.find((w) => w.name === config.widgetName);
    if (!comboWidget || !node.outputs || node.outputs.length === 0) return;
    const selectedValue = comboWidget.value;
    const output = node.outputs[0];
    const mapping = config.typeMap[selectedValue] || {
        type: config.defaultType || '*',
        name: ''
    };
    const newType = mapping.type;
    const newName = mapping.name;
    output.type = newType;
    output.name = newName;
    const graph = node.graph;
    if (!graph || app.configuringGraph) return;
    updatingNodes.add(node);
    try {
        if (output.links && output.links.length > 0) {
            const linksToRemove = [];
            for (const linkId of output.links) {
                const link = graph.links?.[linkId] ?? graph.links?.get?.(linkId);
                if (link) {
                    const targetNode = graph.getNodeById(link.target_id);
                    if (targetNode && targetNode.inputs && targetNode.inputs[link.target_slot]) {
                        const targetInput = targetNode.inputs[link.target_slot];
                        if (!LiteGraph.isValidConnection(newType, targetInput.type)) {
                            linksToRemove.push(linkId);
                        }
                    }
                }
            }
            for (const linkId of linksToRemove) graph.removeLink(linkId);
        }
        if (output.links && output.links.length > 0) {
            const linkColor = LGraphCanvas.link_type_colors[newType];
            for (const linkId of output.links) {
                const link = graph.links?.[linkId] ?? graph.links?.get?.(linkId);
                if (!link) continue;
                link.type = newType;
                if (linkColor) link.color = linkColor;
            }
        }
        node.setDirtyCanvas?.(true, true);
    } finally {
        updatingNodes.delete(node);
    }
}
app.registerExtension({
    name: 'EclipseNova.conversionNodes',
    async beforeRegisterNodeDef(nodeType, nodeData, _app) {
        const config = CONVERSION_NODES[nodeData.name];
        if (!config) return;
        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const ret = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;
            const node = this;
            const refresh = () => updateOutputTypeFromWidget(node, config);
            const origOnAdded = node.onAdded;
            node.onAdded = function () {
                const addedRet = origOnAdded ? origOnAdded.apply(this, arguments) : undefined;
                refresh();
                return addedRet;
            };
            const comboWidget = node.widgets?.find((w) => w.name === config.widgetName);
            if (comboWidget) {
                const origCb = comboWidget.callback;
                comboWidget.callback = function () {
                    if (origCb) origCb.apply(this, arguments);
                    refresh();
                };
            }
            const origOnConfigure = node.onConfigure;
            node.onConfigure = function () {
                const configureRet = origOnConfigure ? origOnConfigure.apply(this, arguments) : undefined;
                refresh();
                return configureRet;
            };
            const origOnGraphConfigured = node.onGraphConfigured;
            node.onGraphConfigured = function () {
                const ret = origOnGraphConfigured?.apply(this, arguments);
                // Some frontends dispatch this hook before clearing the flag.
                const afterConfigure = () => {
                    if (!node.graph) return;
                    if (app.configuringGraph) requestAnimationFrame(afterConfigure);
                    else refresh();
                };
                afterConfigure();
                return ret;
            };
            const origOnConnectionsChange = node.onConnectionsChange;
            node.onConnectionsChange = function () {
                const connectionRet = origOnConnectionsChange
                    ? origOnConnectionsChange.apply(this, arguments)
                    : undefined;
                refresh();
                return connectionRet;
            };
            refresh();
            return ret;
        };
    },
});
