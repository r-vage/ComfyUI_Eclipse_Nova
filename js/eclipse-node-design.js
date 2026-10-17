/** Eclipse Nova's independent, user-editable node designs. */
import { app, api } from './comfy/index.js';
import { ensurePanelStyle } from './eclipse-panel-controls.js';
import { showEclipseToast } from './eclipse-notifications.js';
import { createNodeDesign } from './node-design-theme.js';
import { createThemeLink } from './eclipse-theme-link.js';

export const DESIGN_SETTING = 'EclipseNova.NodeDesign';
function category(id) {
    if (/^(SetNode|GetNode|GetFirstNode|GetAllActiveNode) \[|^Pipe |^Pipe IO |^IO |^Context |Concat Pipe|Generation Data|^Pipe In |DeDuplicate/i.test(id)) return 'pipe';
    if (/Language Model|Smart LM/i.test(id)) return 'text';
    if (/Loader/i.test(id)) return 'loader';
    if (/Mode Bridge/i.test(id)) return 'bridge';
    if (/Repeater|Join|Calculator/i.test(id)) return 'router';
    if (/Lora Stack|Block Swap|VRAM|RAM Cleanup|^Fast |Muter|Bypasser|^Stop |Show Any|Nunchaku PuLID/i.test(id)) return 'tools';
    if (/Resolution|Sampler|Custom Size|ControlNet|Sampler Selection|Load Directory|Filename Generator|VHS Input|Aspect Ratio/i.test(id)) return 'settings';
    if (/String|Prompt|Wildcard|Replace String|Multiline|^Seed /i.test(id)) return 'text';
    if (/Image|Mask|Watermark|Bboxes|Detection|Convert To Batch|To List|To Batch/i.test(id)) return 'image';
    if (/Video Clip|Seamless Join/i.test(id)) return 'video';
    if (/Passer|Switch|IF A|^Boolean |^Float |^Integer |Multi-Switch/i.test(id)) return 'router';
    if (/Folder|Filename Prefix|^Add Folder|^Project Folder/i.test(id)) return 'folder';
    return 'tools';
}

const themeLink = createThemeLink({ app, api,
    notice: message => showEclipseToast('Nova theme link', message),
});
const design = createNodeDesign({ app, api, settingId: DESIGN_SETTING,
    category: ['Eclipse Nova', 'Appearance'], route: '/eclipse-nova', prefix: '--en-',
    dataset: 'eclipseNovaDesign', suffix: ' [Eclipse Nova]', nodeCategory: category, colorTitlesOnCreate: true, scopeControls: true,
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
