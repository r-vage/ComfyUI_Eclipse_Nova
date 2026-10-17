import {
    app,
    api
} from './comfy/index.js';
import { showEclipseToast } from './eclipse-notifications.js';
import {
    isVueMode,
} from './eclipse-widget-utils.js';
import { adaptNestedMenuItems } from './eclipse-context-menu-utils.js';
import { setUseSliders } from './eclipse-panel-numbers.js';
import { isVueClassicNodeContextMenuActive } from './eclipse-vue-classic-node-context-menu.js';
import {
    createCanonicalVueNodeSetting,
    hasNativeVueNodeSetting,
    loadLegacyVueNodeConfig,
    persistCanonicalVueNodeSetting,
    resolveCanonicalVueNodeSetting,
    VUE_NODE_SETTING_DEFINITIONS
} from './eclipse-vue-node-settings.js';

const HIDE_NODE_STATE_BADGES_CLASS = 'eclipse-hide-node-state-badges';
const GENERIC_SETTINGS_CATEGORY = ['Eclipse Nova', 'General'];
const hideStatusSetting = VUE_NODE_SETTING_DEFINITIONS.hideStatusBadges;

function connectNode(sourceNode, ...args) {
    const connect = sourceNode.connect;
    return connect.apply(sourceNode, args);
}

let eclipseConfigPromise;

async function loadEclipseConfig() {
    if (!eclipseConfigPromise) {
        eclipseConfigPromise = api.fetchApi('/eclipse-nova/config/all')
            .then(async (response) => response.ok ? response.json() : {})
            .catch((error) => {
                console.error('[Eclipse Nova] Failed to fetch configuration:', error);
                return {};
            });
    }
    return eclipseConfigPromise;
}

function injectNodeStateBadgeStyles() {
    if (document.getElementById('eclipse-node-state-badge-styles')) return;
    const style = document.createElement('style');
    style.id = 'eclipse-node-state-badge-styles';
    const nodeBadge = [
        '.lg-node-header[data-testid^="node-header-"]',
        '> div[class~="flex"][class~="min-w-0"][class~="items-center"][class~="justify-between"]',
        '> div[class~="flex"][class~="min-w-max"][class~="items-center"][class~="rounded-sm"]' +
        '[class~="bg-node-component-surface"][class~="text-xs"]',
    ].join(' ');
    style.textContent = [
        `html.${HIDE_NODE_STATE_BADGES_CLASS} ${nodeBadge} {`,
        '  display: none !important;',
        '}',
    ].join('\n');
    document.head.appendChild(style);
}

function setNodeStateBadgesHidden(hidden) {
    document.documentElement.classList.toggle(HIDE_NODE_STATE_BADGES_CLASS, hidden);
}

function getElFunction() {
    return 'function' == typeof $el ? $el : function (tag, props, children) {
        let options = props;
        Array.isArray(props) && ((children = props), (options = {}));
        const [tagName, ...classes] = tag.split('.'), el = document.createElement(tagName);
        for (const cls of classes) el.classList.add(cls);
        if (options) {
            options.style && Object.assign(el.style, options.style);
            for (const [key, val] of Object.entries(options)) 'style' !== key && (key.startsWith('on') && 'function' == typeof val ? el.addEventListener(key.slice(2).toLowerCase(), val) : 'children' !== key && (el[key] = val));
        }
        if (children)
            for (const child of children) 'string' == typeof child ? el.appendChild(document.createTextNode(child)) : child instanceof Node && el.appendChild(child);
        return el;
    };
}

function rgbToHex(r, g, b) {
    return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
}
window.eclipseNova_rgb = (r, g, b) => {
    const hex = rgbToHex(Math.round(r), Math.round(g), Math.round(b));
    console.log(`rgb(${r}, ${g}, ${b}) → ${hex}`);
    return hex;
};

function shadeHexColor(hex, amount = -0.2) {
    hex.startsWith('#') && (hex = hex.slice(1));
    let r = parseInt(hex.slice(0, 2), 16),
        g = parseInt(hex.slice(2, 4), 16),
        b = parseInt(hex.slice(4, 6), 16);
    return ((r = Math.max(0, Math.min(255, r + 100 * amount))), (g = Math.max(0, Math.min(255, g + 100 * amount))), (b = Math.max(0, Math.min(255, b + 100 * amount))), rgbToHex(r, g, b));
}

function applyCustomColor(node, applyColor) {
    const canvas = LGraphCanvas.active_canvas,
        selectedNodes = canvas?.selected_nodes,
        targets = selectedNodes && Object.keys(selectedNodes).length > 1 ? Object.values(selectedNodes) : [node];
    targets.forEach(applyColor);
    if (canvas?.setDirty) canvas.setDirty(true, true);
    else node.setDirtyCanvas?.(true, true);
}

let customColorInput = null;
let customColorSession = null;

function getCustomColorTargets(node) {
    const selectedNodes = LGraphCanvas.active_canvas?.selected_nodes;
    return selectedNodes && Object.keys(selectedNodes).length > 1 ? Object.values(selectedNodes) : [node];
}

function updateCustomColorSession(value) {
    const session = customColorSession;
    if (!session) return;
    if (!session.started) {
        session.graph?.beforeChange?.();
        session.started = true;
    }
    for (const target of session.targets) session.applyColor(target, value);
    const canvas = LGraphCanvas.active_canvas;
    if (canvas?.setDirty) canvas.setDirty(true, true);
    else session.node.setDirtyCanvas?.(true, true);
}

function finishCustomColorSession() {
    const session = customColorSession;
    if (!session) return;
    customColorSession = null;
    if (session.started) session.graph?.afterChange?.();
}

function getCustomColorInput() {
    if (customColorInput) return customColorInput;
    customColorInput = document.createElement('input');
    customColorInput.type = 'color';
    customColorInput.style.cssText = 'position:fixed;left:50%;top:50%;width:1px;height:1px;opacity:0.01;pointer-events:none;';
    customColorInput.addEventListener('input', (event) => {
        updateCustomColorSession(event.target.value);
    });
    customColorInput.addEventListener('change', (event) => {
        updateCustomColorSession(event.target.value);
        finishCustomColorSession();
    });
    customColorInput.addEventListener('cancel', finishCustomColorSession);
    customColorInput.addEventListener('blur', () => {
        setTimeout(() => {
            if (customColorSession?.started) finishCustomColorSession();
        }, 0);
    });
    document.body.appendChild(customColorInput);
    return customColorInput;
}

function openCustomColorInput(node, applyColor) {
    finishCustomColorSession();
    const input = getCustomColorInput();
    customColorSession = {
        node,
        graph: node.graph,
        targets: getCustomColorTargets(node),
        applyColor,
        started: false,
    };
    input.value = /^#[0-9a-f]{6}$/i.test(node.bgcolor || '') ? node.bgcolor : '#000000';
    try {
        if (typeof input.showPicker === 'function') input.showPicker();
        else input.click();
    } catch {
        input.click();
    }
}
if ((app.registerExtension({
        name: 'EclipseNova.LogLevel',
        async init(appRef) {
            const config = await loadEclipseConfig();
            const currentLevel = config.log_level || 'warning';
            let initialized = false;
            appRef.ui.settings.addSetting({
                id: 'EclipseNova.LogLevel',
                category: [...GENERIC_SETTINGS_CATEGORY, 'LogLevel'],
                name: '📝 Log Level',
                type: 'combo',
                tooltip: 'Set the logging verbosity level. Changes are saved to config.json and applied immediately.\n\nerror: Only critical errors\nwarning: Errors + warnings\ninfo: Errors + warnings + general messages\ndebug: All messages including detailed debug info',
                defaultValue: currentLevel,
                options: ['error', 'warning', 'info', 'debug'],
                sortOrder: 200,
                async onChange(val) {
                    if (!initialized) {
                        initialized = true;
                        return;
                    }
                    try {
                        const resp = await api.fetchApi('/eclipse-nova/config/log_level', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                log_level: val
                            }),
                        });
                        if (resp.ok) {
                            const result = await resp.json();
                            result.success ? console.log(`[Eclipse Nova] Log level changed to: ${val}`) : console.error('[Eclipse Nova] Failed to update log level:', result.error);
                            if (!result.success) showEclipseToast('Eclipse Nova settings', 'Could not save the log level.');
                        } else {
                            console.error('[Eclipse Nova] Server error updating log level:', resp.status);
                            showEclipseToast('Eclipse Nova settings', 'Could not save the log level.');
                        }
                    } catch (err) {
                        console.error('[Eclipse Nova] Failed to update log level:', err);
                        showEclipseToast('Eclipse Nova settings', 'Could not save the log level.');
                    }
                },
            });
        },
    }), app.registerExtension({
        name: 'EclipseNova.HideNodeStateBadges',
        async init(appRef) {
            const hasNativeSetting = hasNativeVueNodeSetting(
                appRef,
                hideStatusSetting
            );
            const config = await loadLegacyVueNodeConfig();
            const resolved = resolveCanonicalVueNodeSetting(
                appRef,
                hideStatusSetting,
                config
            );
            if (!hasNativeSetting) {
                injectNodeStateBadgeStyles();
                appRef.ui.settings.addSetting(createCanonicalVueNodeSetting(
                    hideStatusSetting,
                    (value) => {
                        setNodeStateBadgesHidden(value === true);
                    }
                ));
                setNodeStateBadgesHidden(resolved.value);
            }
            await persistCanonicalVueNodeSetting(
                appRef,
                hideStatusSetting,
                resolved
            );
        },
    }), app.registerExtension({
        name: 'EclipseNova.UseSliders',
        async init(appRef) {
            const config = await loadEclipseConfig();
            const currentVal = config.use_sliders === true;
            setUseSliders(currentVal);
            let initialized = false;
            appRef.ui.settings.addSetting({
                id: 'EclipseNova.UseSliders',
                category: [...GENERIC_SETTINGS_CATEGORY, 'UseSliders'],
                name: '🎚️ Use Sliders',
                type: 'boolean',
                tooltip: 'Add sliders to bounded numeric fields in Eclipse Nova panels (steps, cfg, denoise, image adjustments, etc.). Applies immediately. Exact values can still be typed; seeds keep their text controls.',
                defaultValue: currentVal,
                sortOrder: 100,
                async onChange(val) {
                    if (initialized)
                        try {
                            const resp = await api.fetchApi('/eclipse-nova/config/update', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json'
                                },
                                body: JSON.stringify({
                                    use_sliders: val
                                }),
                            });
                            if (resp.ok && (await resp.json()).success) {
                                setUseSliders(val);
                            } else showEclipseToast('Eclipse Nova settings', 'Could not save Use Sliders.');
                        } catch (err) {
                            console.error('[Eclipse Nova] Failed to update use_sliders:', err);
                            showEclipseToast('Eclipse Nova settings', 'Could not save Use Sliders.');
                        }
                },
            });
            // Root config is authoritative, even if ComfyUI saved an older UI value.
            await appRef.ui.settings.setSettingValueAsync?.('EclipseNova.UseSliders', currentVal);
            initialized = true;
        },
    }), app.registerExtension({
        name: 'EclipseNova.colors',
        async init() {
            const origOnMenuNodeColors = LGraphCanvas.onMenuNodeColors;
            'function' == typeof origOnMenuNodeColors ? (LGraphCanvas.onMenuNodeColors = function (values, options, event, parentMenu, node) {
                const result = origOnMenuNodeColors.apply(this, arguments),
                    $el = getElFunction(),
                    menuRoot = parentMenu?.current_submenu?.root;
                if (!menuRoot) return (console.debug('[Eclipse Nova] [Colors] Could not access menu submenu root'), result);
                const isGroup = node instanceof LGraphGroup;
                try {
                    if (!isGroup) {
                        menuRoot.append($el('div.litemenu-entry.submenu', [$el('label', {
                            style: {
                                position: 'relative',
                                overflow: 'hidden',
                                display: 'block',
                                paddingLeft: '4px',
                                borderLeft: '8px solid #222',
                            },
                        }, ['Custom Title Color', $el('input', {
                            type: 'color',
                            value: node.bgcolor,
                            style: {
                                position: 'absolute',
                                right: '200%'
                            },
                            oninput(ev) {
                                const titleColor = shadeHexColor(ev.target.value);
                                applyCustomColor(node, (target) => {
                                    target.color = titleColor;
                                });
                            },
                            onchange(ev) {
                                console.log(`[Eclipse Nova] Title: ${node.color}`);
                            },
                        }), ], ), ]), );
                        menuRoot.append($el('div.litemenu-entry.submenu', [$el('label', {
                            style: {
                                position: 'relative',
                                overflow: 'hidden',
                                display: 'block',
                                paddingLeft: '4px',
                                borderLeft: '8px solid #222',
                            },
                        }, ['Custom Background Color', $el('input', {
                            type: 'color',
                            value: node.bgcolor,
                            style: {
                                position: 'absolute',
                                right: '200%'
                            },
                            oninput(ev) {
                                const backgroundColor = ev.target.value;
                                applyCustomColor(node, (target) => {
                                    target.bgcolor = backgroundColor;
                                });
                            },
                            onchange(ev) {
                                console.log(`[Eclipse Nova] BG: ${ev.target.value}`);
                            },
                        }), ], ), ]), );
                        menuRoot.append($el('div.litemenu-entry.submenu', [$el('label', {
                            style: {
                                position: 'relative',
                                overflow: 'hidden',
                                display: 'block',
                                paddingLeft: '4px',
                                borderLeft: '8px solid #222',
                            },
                        }, ['Custom Title + Background Colors', $el('input', {
                            type: 'color',
                            value: node.bgcolor,
                            style: {
                                position: 'absolute',
                                right: '200%'
                            },
                            oninput(ev) {
                                const backgroundColor = ev.target.value,
                                    titleColor = shadeHexColor(backgroundColor);
                                applyCustomColor(node, (target) => {
                                    target.bgcolor = backgroundColor;
                                    target.color = titleColor;
                                });
                            },
                            onchange(ev) {
                                console.log(`[Eclipse Nova] All → BG: ${node.bgcolor}, Title: ${node.color}`);
                            },
                        }), ], ), ]), );
                    }
                    if (isGroup) {
                        menuRoot.append($el('div.litemenu-entry.submenu', [$el('label', {
                            style: {
                                position: 'relative',
                                overflow: 'hidden',
                                display: 'block',
                                paddingLeft: '4px',
                                borderLeft: '8px solid #222',
                            },
                        }, ['Color Group', $el('input', {
                            type: 'color',
                            value: node.bgcolor,
                            style: {
                                position: 'absolute',
                                right: '200%'
                            },
                            oninput(ev) {
                                node.bgcolor = ev.target.value;
                                node.color = shadeHexColor(node.bgcolor);
                                node.setDirtyCanvas(true, true);
                            },
                        }), ], ), ]), );
                        menuRoot.append($el('div.litemenu-entry.submenu', [$el('label', {
                            style: {
                                position: 'relative',
                                overflow: 'hidden',
                                display: 'block',
                                paddingLeft: '4px',
                                borderLeft: '8px solid #222',
                            },
                        }, ['Color All Title', $el('input', {
                            type: 'color',
                            value: node.bgcolor,
                            style: {
                                position: 'absolute',
                                right: '200%'
                            },
                            oninput(ev) {
                                node.recomputeInsideNodes();
                                node.color = shadeHexColor(ev.target.value);
                                node._nodes.forEach((child) => {
                                    child.color = shadeHexColor(ev.target.value);
                                    child.setDirtyCanvas(true, true);
                                });
                                node.setDirtyCanvas(true, true);
                            },
                        }), ], ), ]), );
                        menuRoot.append($el('div.litemenu-entry.submenu', [$el('label', {
                            style: {
                                position: 'relative',
                                overflow: 'hidden',
                                display: 'block',
                                paddingLeft: '4px',
                                borderLeft: '8px solid #222',
                            },
                        }, ['Color All BG', $el('input', {
                            type: 'color',
                            value: node.bgcolor,
                            style: {
                                position: 'absolute',
                                right: '200%'
                            },
                            oninput(ev) {
                                node.recomputeInsideNodes();
                                node.bgcolor = ev.target.value;
                                node._nodes.forEach((child) => {
                                    child.bgcolor = ev.target.value;
                                    child.setDirtyCanvas(true, true);
                                });
                                node.setDirtyCanvas(true, true);
                            },
                        }), ], ), ]), );
                        menuRoot.append($el('div.litemenu-entry.submenu', [$el('label', {
                            style: {
                                position: 'relative',
                                overflow: 'hidden',
                                display: 'block',
                                paddingLeft: '4px',
                                borderLeft: '8px solid #222',
                            },
                        }, ['Color All', $el('input', {
                            type: 'color',
                            value: node.bgcolor,
                            style: {
                                position: 'absolute',
                                right: '200%'
                            },
                            oninput(ev) {
                                node.recomputeInsideNodes();
                                node.bgcolor = ev.target.value;
                                node.color = shadeHexColor(node.bgcolor);
                                node._nodes.forEach((child) => {
                                    child.bgcolor = ev.target.value;
                                    child.color = shadeHexColor(node.bgcolor);
                                    child.setDirtyCanvas(true, true);
                                });
                                node.setDirtyCanvas(true, true);
                            },
                        }), ], ), ]), );
                    }
                } catch (err) {
                    console.debug('[Eclipse Nova] [Colors] Error adding custom color pickers:', err);
                }
                return result;
            }) : console.debug('[Eclipse Nova] [Colors] LGraphCanvas.onMenuNodeColors not available');
        },
    }), !LGraphCanvas.prototype.eclipseNovaSetNodeDimension)) {
    if (((window.eclipseNova_newNodeMenuAPIUsed = false), !document.getElementById('eclipse-dialog-style'))) {
        const styleEl = document.createElement('style');
        styleEl.id = 'eclipse-dialog-style';
        styleEl.innerHTML = '\n    .eclipse-dialog {\n      position: fixed;\n      top: 10px;\n      left: 10px;\n      min-height: 1em;\n      background-color: var(--comfy-menu-bg, #222);\n      color: var(--descrip-text, #ddd);\n      font-size: 1.0rem;\n      box-shadow: 0 0 7px black !important;\n      z-index: 10000;\n      display: grid;\n      border-radius: 7px;\n      padding: 7px 7px;\n    }\n    .eclipse-dialog .name { display:inline-block; font-size:14px; padding:0; justify-self:center; }\n    .eclipse-dialog input, .eclipse-dialog textarea, .eclipse-dialog select { margin:3px; min-width:60px; min-height:1.5em; background-color: var(--comfy-input-bg, #333); border:2px solid var(--border-color, #444); color: var(--input-text, #fff); border-radius:14px; padding-left:10px; outline:none; }\n    .eclipse-dialog button { margin-top:3px; vertical-align:top; background-color:#999; border:0; padding:4px 18px; border-radius:20px; cursor:pointer; }\n    ';
        document.head.appendChild(styleEl);
    }
    var _eclipseLastMouse = {
        x: 0,
        y: 0
    };
    document.addEventListener('pointerdown', function (ev) {
        _eclipseLastMouse.x = ev.clientX;
        _eclipseLastMouse.y = ev.clientY;
    }, true, );
    LGraphCanvas.prototype.eclipseCreateDialog = function (html, onOk, onCancel) {
        var dialog = document.createElement('div');
        dialog.is_modified = false;
        dialog.className = 'eclipse-dialog';
        dialog.innerHTML = html + "<button id='ok'>OK</button>";
        dialog.close = function () {
            dialog.parentNode && dialog.parentNode.removeChild(dialog);
        };
        var inputs = Array.from(dialog.querySelectorAll('input, select'));
        inputs.forEach((inp) => {
            inp.addEventListener('keydown', function (ev) {
                if (((dialog.is_modified = true), 27 == ev.keyCode))(onCancel && onCancel(), dialog.close());
                else if (13 == ev.keyCode)
                    (onOk && onOk(dialog, inputs.map((inp) => inp.value), ), dialog.close());
                else if (13 != ev.keyCode && 'textarea' != ev.target.localName) return;
                ev.preventDefault();
                ev.stopPropagation();
            });
        });
        if (_eclipseLastMouse.x || _eclipseLastMouse.y) {
            dialog.style.left = _eclipseLastMouse.x - 20 + 'px';
            dialog.style.top = _eclipseLastMouse.y - 20 + 'px';
        } else {
            dialog.style.left = 0.5 * window.innerWidth - 60 + 'px';
            dialog.style.top = 0.5 * window.innerHeight - 20 + 'px';
        }
        dialog.querySelector('#ok').addEventListener('click', function () {
            onOk && onOk(dialog, inputs.map((inp) => inp.value), );
            dialog.close();
        });
        document.body.appendChild(dialog);
        inputs && inputs[0].focus();
        var leaveTimeout = null;
        return (dialog.addEventListener('mouseleave', function (ev) {
            LiteGraph.dialog_close_on_mouse_leave && !dialog.is_modified && LiteGraph.dialog_close_on_mouse_leave && (leaveTimeout = setTimeout(dialog.close, LiteGraph.dialog_close_on_mouse_leave_delay));
        }), dialog.addEventListener('mouseenter', function (ev) {
            LiteGraph.dialog_close_on_mouse_leave && leaveTimeout && clearTimeout(leaveTimeout);
        }), dialog);
    };
    LGraphCanvas.prototype.eclipseNovaSetNodeDimension = function (targetNode) {
        const curWidth = targetNode.size[0],
            curHeight = targetNode.size[1];
        let html = "<input type='text' class='width' value='" + curWidth + "'></input>";
        html += "<input type='text' class='height' value='" + curHeight + "'></input>";
        LGraphCanvas.prototype.eclipseCreateDialog("<span class='name'>Width/Height</span>" + html, function (dialog, values) {
            var newWidth = Number(values[0]) || curWidth,
                newHeight = Number(values[1]) || curHeight;
            let minSize = targetNode.computeSize();
            var finalWidth = Math.max(minSize[0], newWidth),
                finalHeight = Math.max(minSize[1], newHeight);
            targetNode.setSize([finalWidth, finalHeight]);
            var vueEl = document.querySelector('[data-node-id="' + targetNode.id + '"]');
            if (vueEl) {
                var titleHeight = ('undefined' != typeof LiteGraph && LiteGraph.NODE_TITLE_HEIGHT) || 30;
                vueEl.style.setProperty('--node-width', finalWidth + 'px');
                vueEl.style.setProperty('--node-height', finalHeight + titleHeight + 'px');
            }
            dialog.parentNode && dialog.parentNode.removeChild(dialog);
            targetNode.setDirtyCanvas(true, true);
        }, null, );
    };
    LGraphCanvas.prototype.eclipseReloadNode = function (sourceNode) {
        try {
            const CONVERTED_TYPE = 'converted-widget',
                CONVERTED_MARKER = Symbol();

            function getInputDef(widgetName, node) {
                const {
                    nodeData
                } = node.constructor;
                return nodeData?.input?.required[widgetName] ?? nodeData?.input?.optional?.[widgetName];
            }

            function hideWidget(node, widget, suffix = '') {
                widget.origType = widget.type;
                widget.origComputeSize = widget.computeSize;
                widget.origSerializeValue = widget.serializeValue;
                widget.computeSize = () => [0, -4];
                widget.type = CONVERTED_TYPE + suffix;
                widget.serializeValue = () => {
                    if (!node.inputs) return;
                    const inputSlot = node.inputs.find((inp) => inp.widget?.name === widget.name);
                    return inputSlot && inputSlot.link ? (widget.origSerializeValue ? widget.origSerializeValue() : widget.value) : undefined;
                };
                if (widget.linkedWidgets) {
                    for (const linked of widget.linkedWidgets) hideWidget(node, linked, ':' + widget.name);
                }
            }

            function convertToInput(node, widget, inputDef) {
                hideWidget(node, widget);
                const {
                    type: inputType
                } = (function (def) {
                    let first = def[0];
                    return (first instanceof Array && (first = 'COMBO'), {
                        type: first
                    });
                })(inputDef), prevSize = node.size;
                node.addInput(widget.name, inputType, {
                    widget: {
                        name: widget.name,
                        [CONVERTED_MARKER]: () => inputDef
                    }
                });
                for (const w of node.widgets) w.last_y += LiteGraph.NODE_SLOT_HEIGHT;
                node.setSize([Math.max(prevSize[0], node.size[0]), Math.max(prevSize[1], node.size[1])]);
            }
            const {
                title,
                color,
                bgcolor
            } = sourceNode.properties.origVals || sourceNode, savedProps = {
                size: [...sourceNode.size],
                color,
                bgcolor,
                pos: [...sourceNode.pos]
            }, origNode = sourceNode, inputConns = [], outputConns = [];
            if (sourceNode.inputs) {
                for (const inp of sourceNode.inputs ?? []) {
                    if (inp.link) {
                        const inputName = inp.name,
                            slotIdx = sourceNode.findInputSlot(inputName),
                            srcNode = sourceNode.getInputNode(slotIdx),
                            linkInfo = sourceNode.getInputLink(slotIdx);
                        inputConns.push([linkInfo.origin_slot, srcNode, inputName]);
                    }
                }
            }
            if (sourceNode.outputs) {
                for (const output of sourceNode.outputs) {
                    if (output.links) {
                        const outputName = output.name;
                        for (const linkId of output.links) {
                            const linkInfo = app.graph.links[linkId],
                                targetNode = app.graph._nodes_by_id[linkInfo.target_id];
                            outputConns.push([outputName, targetNode, linkInfo.target_slot]);
                        }
                    }
                }
            }
            app.graph.remove(sourceNode);
            const newNode = app.graph.add(LiteGraph.createNode(origNode.constructor.type, title, savedProps));
            if (newNode?.constructor?.hasOwnProperty('ttNnodeVersion')) {
                newNode.properties.ttNnodeVersion = newNode.constructor.ttNnodeVersion;
            }
            let widgetValues = origNode.widgets_values;
            if (widgetValues) {
                let foundValid = false;
                const isAscending = widgetValues.length <= newNode.widgets.length;
                let searchIdx = isAscending ? 0 : widgetValues.length - 1;
                const validateValue = (val, widget) => !['', null].includes(val) || ('button' !== widget.type && 'converted-widget' !== widget.type) ? ('boolean' == typeof val && widget.options?.on && widget.options?.off) || widget.options?.values?.includes(val) ? {
                    value: val,
                    isValid: true
                } : !widget.inputEl || ('string' != typeof val && val !== widget.value) ? !isNaN(val) && ((val = parseFloat(val)), widget.options?.min <= val && val <= widget.options?.max) ? {
                    value: val,
                    isValid: true
                } : {
                    value: widget.value,
                    isValid: false
                } : {
                    value: val,
                    isValid: true
                } : {
                    value: val,
                    isValid: true
                };

                function applyWidgetValue(idx) {
                    const origWidget = origNode.widgets[idx];
                    let newWidget = newNode.widgets[idx],
                        pos = searchIdx;
                    if (newWidget.name === origWidget.name && (newWidget.type === origWidget.type || 'ttNhidden' === origWidget.type || 'ttNhidden' === newWidget.type)) {
                        for (;
                            (isAscending ? pos < widgetValues.length : pos >= 0) && !foundValid;) {
                            let result = validateValue(widgetValues[pos], newWidget),
                                val = result.value;
                            if (((foundValid = result.isValid), foundValid && NaN !== val)) {
                                newWidget.value = val;
                                break;
                            }
                            pos += isAscending ? 1 : -1;
                        }
                        if (isAscending) {
                            if (pos === searchIdx) searchIdx++;
                            if (pos === searchIdx + 1) {
                                searchIdx++;
                                searchIdx++;
                            }
                        } else {
                            if (pos === searchIdx) searchIdx--;
                            if (pos === searchIdx - 1) {
                                searchIdx--;
                                searchIdx--;
                            }
                        }
                    }
                }
                if (isAscending) {
                    for (let idx = 0; idx < newNode.widgets.length; idx++) applyWidgetValue(idx);
                } else {
                    for (let idx = newNode.widgets.length - 1; idx >= 0; idx--) applyWidgetValue(idx);
                }
            } else {
                newNode.widgets.forEach((widget, idx) => {
                    let found = false;
                    for (; idx < origNode.widgets.length && !found;) {
                        const origWidget = origNode.widgets[idx];
                        if (widget.type === origWidget.type) {
                            widget.value = origWidget.value;
                            found = true;
                        }
                        idx++;
                    }
                });
            }
            (function () {
                for (const widget of origNode.widgets) {
                    if (widget.type === CONVERTED_TYPE) {
                        const inputDef = getInputDef(widget.name, origNode),
                            targetWidget = newNode.widgets.find((w) => w.name === widget.name);
                        if (targetWidget && !newNode?.inputs?.find((inp) => inp.name === widget.name)) {
                            convertToInput(newNode, targetWidget, inputDef);
                        }
                    }
                }
                // These LiteGraph connect() calls restore in-memory workflow
                // edges and do not perform network communication.
                for (const conn of inputConns) {
                    const [originSlot, srcNode, inputName] = conn;
                    connectNode(srcNode, originSlot, newNode.id, inputName);
                }
                for (const conn of outputConns) {
                    const [outputName, targetNode, targetSlot] = conn;
                    connectNode(newNode, outputName, targetNode, targetSlot);
                }
            })();
            newNode.setSize(savedProps.size);
            if (typeof newNode.onResize === 'function') newNode.onResize([0, 0]);
            newNode.setDirtyCanvas(true, true);
        } catch (err) {
            console.debug('eclipse: eclipseReloadNode exception', err);
        }
    };
}
app.registerExtension({
    name: 'EclipseNova.nodeMenuItems',
    getNodeMenuItems(node) {
        // Node menu via hook (no position control, but no duplication issues)
        const rawItems = window._eclipseNovaBuildNodeMenuItems?.(node) || [];
        const cleaned = isVueClassicNodeContextMenuActive()
            ? rawItems
            : adaptNestedMenuItems(rawItems);
        if (!cleaned.length) return [];
        return [null, {
            content: '🌒 Eclipse Nova',
            has_submenu: true,
            submenu: { title: 'Eclipse Nova', options: cleaned },
        }];
    },
    getCanvasMenuItems() {
        // Collect from canvas menu providers
        const providerItems = [];
        const providers = window._eclipseNovaCanvasMenuProviders || [];
        for (const fn of providers) {
            try {
                const items = fn();
                if (items?.length) providerItems.push(...items);
            } catch (e) {
                console.debug('eclipse: canvas menu provider error', e);
            }
        }
        // Clean separators
        const cleaned = [];
        for (const item of providerItems) {
            if (item === null) {
                if (cleaned.length > 0 && cleaned[cleaned.length - 1] !== null) cleaned.push(null);
            } else {
                cleaned.push(item);
            }
        }
        while (cleaned.length && cleaned[cleaned.length - 1] === null) cleaned.pop();
        if (!cleaned.length) return [];
        const rendererItems = adaptNestedMenuItems(cleaned);
        return [null, {
            content: '🌒 Eclipse Nova',
            has_submenu: true,
            submenu: { title: 'Eclipse Nova', options: rendererItems },
        }];
    },
    setup() {
        // Shared helper: build Eclipse submenu items for a node
        function buildNodeMenuItems(node) {
            const items = [{
                content: 'Node Dimensions',
                callback: () => {
                    LGraphCanvas.prototype.eclipseNovaSetNodeDimension(node);
                },
            }, {
                content: 'Reload Node',
                callback: () => {
                    try {
                        LGraphCanvas.prototype.eclipseReloadNode(node);
                    } catch (err) {
                        console.debug('eclipse: Reload Node failed', err);
                    }
                },
            }];
            if (isVueMode() && !(node instanceof LGraphGroup)) {
                items.push(null, {
                    content: 'Custom Title Color',
                    callback: () => {
                        openCustomColorInput(node, (target, color) => {
                            target.color = shadeHexColor(color);
                        });
                    },
                }, {
                    content: 'Custom Background Color',
                    callback: () => {
                        openCustomColorInput(node, (target, color) => {
                            target.bgcolor = color;
                        });
                    },
                }, {
                    content: 'Custom Title + Background Colors',
                    callback: () => {
                        openCustomColorInput(node, (target, color) => {
                            target.bgcolor = color;
                            target.color = shadeHexColor(color);
                        });
                    },
                });
            }
            const providers = window._eclipseNovaMenuProviders || [];
            for (const fn of providers) {
                try {
                    const providerItems = fn(node);
                    if (providerItems?.length) items.push(...providerItems);
                } catch (e) {
                    console.debug('eclipse: menu provider error', e);
                }
            }
            // Clean separators
            const cleaned = [];
            for (const item of items) {
                if (item === null) {
                    if (cleaned.length > 0 && cleaned[cleaned.length - 1] !== null) cleaned.push(null);
                } else {
                    cleaned.push(item);
                }
            }
            while (cleaned.length && cleaned[cleaned.length - 1] === null) cleaned.pop();
            return cleaned;
        }
        window._eclipseNovaBuildNodeMenuItems = buildNodeMenuItems;
    },
});
