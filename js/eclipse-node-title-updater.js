import { app, api } from './comfy/index.js';

app.registerExtension({
    name: "EclipseNova.NodeTitleUpdater",
    async setup(app) {
        api.addEventListener("eclipse-nova/update_node_title", (e) => {
            const detail = e.detail;
            if (!detail) return;
            const nodeId = detail.node_id;
            const title = detail.title;
            const node = app.graph.getNodeById(nodeId);
            if (node) {
                node.title = title;
                app.canvas.draw(true, true);
            }
        });
    }
});
