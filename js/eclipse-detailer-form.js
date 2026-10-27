/** Detection controls for the integrated detailer; shares sampler panel state. */
import { element, button } from './eclipse-panel-controls.js';

export function detectionMode(form, parent) {
    const state = form.state;
    const bar = element('div', 'en-panel-bar'), collapsed = state.editor.modeCollapsed === true;
    bar.dataset.collapsed = String(collapsed); bar.setAttribute('role', 'group'); bar.setAttribute('aria-label', 'Detection mode');
    const toggle = button('', 'Mode', () => form.edit(s => { s.editor.modeCollapsed = !collapsed; }));
    toggle.className = 'en-panel-disclosure'; toggle.dataset.field = 'detection.mode'; toggle.setAttribute('aria-expanded', String(!collapsed));
    toggle.append(element('span', '', collapsed ? '▸' : '▾'), element('span', 'en-panel-bar-label', 'Mode:'));
    if (collapsed) toggle.append(element('span', 'en-panel-summary', ['YOLO',
        ...(state.config.parameters.sam2_enabled ? ['SAM2'] : []),
        ...(state.config.parameters.refine_edges ? ['Edges'] : [])].join(' · ')));
    bar.append(toggle);
    if (!collapsed) {
        const control = button('YOLO', 'YOLO', () => form.edit(s => { if (!s.sectionOpen('detection')) s.toggleSection('detection'); }));
        control.title = 'Open YOLO detection settings. The checkpoint determines boxes or segmentation automatically. Non-None SEGS or BBOXES from the pipe take priority.';
        control.setAttribute('aria-pressed', 'true'); control.dataset.field = 'mode.YOLO'; bar.append(control);
    }
    if (!collapsed) for (const key of ['sam2_enabled', 'refine_edges']) form.extraControl(bar, key);
    parent.append(bar);
}

export function detectionSections(form, parent) {
    const p = form.state.config.parameters;
    const section = (key, label, fields, note) => form.section(parent, key, label, body => {
        const grid = element('div', 'en-panel-grid');
        for (const name of fields) form.extraControl(grid, name);
        body.append(grid);
        if (note) body.append(element('div', 'en-panel-note', note));
    });
    section('detection', 'Detection', ['yolo_model',
        'detection', 'threshold', 'nms_iou', 'bbox_dilation', 'detection_device',
        ...(p.sam2_enabled || p.refine_edges ? ['precision'] : [])],
    'Non-None SEGS or BBOXES in the PIPE take priority over internal YOLO. Empty detections select nothing. Detection text filters YOLO’s trained labels; use SmartLLM for free-text detection.');
    section('selection', 'Region selection', ['selection', ...(p.selection === 'Ordered' ? ['sort_by', 'descending', 'take_start', 'take_count'] : []),
        'box_selection', ...(p.box_selection === 'Indices' ? ['box_indices'] : []), 'crop_factor', 'drop_size'],
    'Selection applies separately to each image, before SAM2. Use the original image without drawn boxes.');
    if (p.sam2_enabled) section('sam', 'SAM2 segmentation', ['sam2_model'],
        'Uses the selected bounding boxes to segment the original image. For SEGS, replaces each mask using its box. SAM2 does not read Detection text.');
    if (p.refine_edges) section('refinement', 'Edge refinement', ['detail_method', 'detail_erode', 'detail_dilate',
        'black_point', 'white_point', ...(p.detail_method === 'Guided filter' ? [] : ['max_megapixels'])],
    p.detail_method === 'ViTMatte' ? 'Uses local models/vitmatte with the image and a trimap from its mask. Detection models are released before diffusion detailing.' : 'Refinement runs before grow/blur.');
    section('regions', 'Mask processing', ['invert_mask', 'mask_grow', 'mask_blur', 'combined', 'bbox_fill', ...(!p.combined ? ['contour_fill'] : [])]);
}

export function detectionSummary(p, key) {
    if (key === 'detection') return `${p.yolo_model} · ${p.detection || 'all'}`;
    if (key === 'sam') return p.sam2_model;
    if (key === 'refinement') return p.detail_method;
    if (key === 'regions') return `${p.combined ? 'Combined' : 'Separate'} · grow ${p.mask_grow} · blur ${p.mask_blur}`;
    if (key === 'selection') return p.selection === 'All' ? 'All regions' : `${p.sort_by} · from ${p.take_start} · ${p.take_count} regions`;
    return null;
}
