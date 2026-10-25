/** Eclipse Nova's independent, user-editable node designs. */
import { app, api } from './comfy/index.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { showEclipseToast } from './eclipse-notifications.js';
import { createNodeDesign } from './node-design-theme.js';
import { createThemeLink } from './eclipse-theme-link.js';

export const DESIGN_SETTING = 'EclipseNova.NodeDesign';

const themeLink = createThemeLink({ app, api,
    notice: message => showEclipseToast('Nova theme link', message),
});
const design = createNodeDesign({ app, api, settingId: DESIGN_SETTING,
    category: ['Eclipse Nova', 'Appearance'], route: '/eclipse-nova', prefix: '--en-',
    dataset: 'eclipseNovaDesign', suffix: ' [Eclipse Nova]', scopeControls: true,
    notice: message => showEclipseToast('Eclipse Nova design', message),
    onDesignApplied: id => themeLink.setTheme(id),
});
export const { applyNodeDesign, applyGraphDesign, applyDesign } = design;
app.registerExtension({
    name: DESIGN_SETTING,
    async setup() {
        design.installNodeDesignHooks(globalThis.LiteGraph?.registered_node_types);
        design.installGraphDesignHook(globalThis.LiteGraph?.LGraph, globalThis.LiteGraph?.LGraphGroup);
        await themeLink.start();
    },
    async init() {
        ensurePanelStyle();
        let config = {};
        try {
            const response = await api.fetchApi('/eclipse-nova/config/all');
            if (!response.ok) throw Error('Could not load the saved node design.');
            config = await response.json();
        } catch (error) { showEclipseToast('Eclipse Nova design', error.message); }
        themeLink.initialize(config);
        await design.initialize(config);
    },
    nodeCreated(node) { applyNodeDesign(node, true); },
    loadedGraphNode(node) { applyNodeDesign(node); },
    afterConfigureGraph() { applyGraphDesign(app.graph); },
});
