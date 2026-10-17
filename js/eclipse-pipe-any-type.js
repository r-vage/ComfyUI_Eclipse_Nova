import {
    app
} from './comfy/index.js';
const PIPE_NODES = {
    'Pipe 12CH Any [Eclipse Nova]': 12,
    'Pipe 24CH Any [Eclipse Nova]': 24,
    'Pipe 36CH Any [Eclipse Nova]': 36,
};
app.registerExtension({
    name: 'EclipseNova.PipeAnyType',
    async beforeRegisterNodeDef(nodeType, nodeData, _app) {
        const channelCount = PIPE_NODES[nodeData.name];
        if (!channelCount) return;
        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated && origOnNodeCreated.apply(this, arguments);
            const node = this;
            node.properties = node.properties || {};
            node.onGraphConfigured = function () {
                this.configured = true;
            };
            const origOnConnectionsChange = node.onConnectionsChange;
            node.onConnectionsChange = function (ioType, slotIndex, isConnected, linkInfo) {
                if (origOnConnectionsChange) origOnConnectionsChange.apply(this, arguments);
                if (!linkInfo || !this.inputs || !this.outputs || !this.graph) return;
                if (slotIndex < 1 || slotIndex > channelCount) return;
                const inp = this.inputs[slotIndex];
                const out = this.outputs[slotIndex];
                if (!inp || !out) return;
                if (isConnected) {
                    if (ioType === LiteGraph.INPUT) {
                    const sourceNode = this.graph.getNodeById(linkInfo.origin_id);
                        if (!sourceNode) return;
                        const sourceOutput = sourceNode.outputs?.[linkInfo.origin_slot];
                        if (!sourceOutput) return;
                        const connType = sourceOutput.type;
                        const linkColor = LGraphCanvas.link_type_colors[connType];
                        inp.type = connType;
                        out.type = connType;
                        out.name = connType;
                    const graphLink = this.graph.links?.[linkInfo.id] ?? this.graph.links?.get?.(linkInfo.id);
                        if (graphLink && linkColor) graphLink.color = linkColor;
                    } else if (ioType === LiteGraph.OUTPUT && inp.link === null) {
                        inp.type = linkInfo.type;
                        out.type = linkInfo.type;
                        out.name = linkInfo.type;
                    }
                } else {
                    const inputEmpty = inp.link === null;
                    const outputEmpty = !out.links || out.links.length === 0;
                    if ((ioType === LiteGraph.INPUT && outputEmpty) || (ioType === LiteGraph.OUTPUT && inputEmpty)) {
                        const origName = `any${slotIndex}`;
                        inp.type = '*';
                        out.type = '*';
                        out.name = origName;
                    }
                }
            };
            node.onAdded = function () {
                for (let i = 1; i <= channelCount; i++) {
                    if (this.inputs[i]) this.inputs[i].type = '*';
                    if (this.outputs[i]) {
                        this.outputs[i].type = '*';
                        this.outputs[i].name = `any${i}`;
                    }
                }
            };
        };
    },
});
