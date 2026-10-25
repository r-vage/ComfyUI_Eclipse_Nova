/** Local theme catalog and event-driven application; no cross-pack state. */
export function createNodeDesign({ app, api, settingId, category, route, prefix, dataset,
    suffix, notice, scopeControls = false, onDesignApplied }) {
    const defaultDesign = 'neutral';
    let designs = {}, active = null, saved = defaultDesign, ready = false, synchronizing = false;
    let revision = 0, pending = Promise.resolve();
    const decoratedTypes = new WeakSet();
    const decoratedGraphs = new WeakSet();
    const decoratedNodes = new WeakSet();
    const titleKey = `${dataset}Title`, backgroundKey = `${dataset}Background`, restoreKey = `${dataset}Restore`;
    const scopes = { theme_regular_nodes: false, theme_groups: false };
    const normalize = value => typeof value === 'string' ? value.toLowerCase().replace(/^#([0-9a-f])([0-9a-f])([0-9a-f])$/, '#$1$1$2$2$3$3') : value;
    const ownedId = node => [node.comfyClass, node.type, node.constructor?.type]
        .find(id => typeof id === 'string' && id.endsWith(suffix));

    const isDefaultColor = (field, value) => value != null && normalize(value) === normalize(
        globalThis.LiteGraph?.[field === 'color' ? 'NODE_DEFAULT_COLOR' : 'NODE_DEFAULT_BGCOLOR']);

    function applyNodeColor(node, field, key, value, created) {
        const properties = node.properties ??= {};
        const current = normalize(node[field]);
        const previous = properties[key] !== undefined ? properties[key] : properties[restoreKey]?.applied?.[field];
        // Only untouched defaults follow the theme. Saved colors without a marker
        // are user choices, even if they happen to match a theme or category color.
        const automatic = !current || (previous !== undefined
            ? previous !== null && current === normalize(previous)
            : created && isDefaultColor(field, current));
        properties[key] = automatic ? value : null;
        if (automatic) node[field] = value;
        return automatic;
    }

    function restoreColors(item, container, fields) {
        const state = container?.[restoreKey];
        if (!state || typeof state !== 'object') return;
        for (const field of fields) {
            if (Object.hasOwn(state.applied ?? {}, field) && normalize(item[field]) === normalize(state.applied[field])) {
                item[field] = state.original[field] ?? undefined;
            }
        }
        delete container[restoreKey];
    }

    function installRestoreHook(node) {
        if (decoratedNodes.has(node)) return;
        decoratedNodes.add(node);
        const original = node.onConfigure;
        const initial = { color: node.color, bgcolor: node.bgcolor };
        node.onConfigure = function (info, ...args) {
            const result = original?.call(this, info, ...args);
            if (!info || (!ownedId(this) && !scopes.theme_regular_nodes && !info.properties?.[restoreKey])) return result;
            // LiteGraph merges properties, so constructor-applied theme markers
            // otherwise survive even when the saved workflow never contained them.
            for (const key of [titleKey, backgroundKey, restoreKey]) {
                if (!Object.hasOwn(info.properties ?? {}, key)) delete this.properties?.[key];
            }
            for (const field of ['color', 'bgcolor']) {
                if (info[field] == null) this[field] = isDefaultColor(field, initial[field]) ? undefined : initial[field];
            }
            applyNodeDesign(this);
            return result;
        };
    }

    function applyNodeDesign(node, created = false) {
        const id = ownedId(node);
        if (!active) return false;
        if (!id && !scopes.theme_regular_nodes) {
            if (scopeControls && node.properties?.[restoreKey]) {
                restoreColors(node, node.properties, ['color', 'bgcolor']);
                for (const key of [titleKey, backgroundKey]) {
                    if (node.properties[key] !== null) delete node.properties[key];
                }
            }
            return false;
        }
        installRestoreHook(node);
        let state;
        if (!id) {
            const properties = node.properties ??= {};
            state = properties[restoreKey] ??= {
                original: { color: node.color ?? null, bgcolor: node.bgcolor ?? null }, applied: {},
            };
        }
        for (const [field, key, value] of [
            ['color', titleKey, active.node.title],
            ['bgcolor', backgroundKey, active.node.background],
        ]) {
            const automatic = applyNodeColor(node, field, key, value, created);
            if (state) {
                if (automatic) state.applied[field] = node[field];
                else delete state.applied[field];
            }
        }
        return true;
    }

    function applyGroupDesign(group) {
        if (!scopeControls || !active) return;
        if (!scopes.theme_groups) return restoreColors(group, group.flags, ['color']);
        const flags = group.flags ??= {};
        const state = flags[restoreKey] ??= { original: { color: group.color ?? null }, applied: {} };
        // Interpolate the requested body/group pairs: 26→60 and 58→80.
        const color = active.node.background.replace(/[0-9a-f]{2}/gi,
            channel => Math.round(parseInt(channel, 16) * 0.625 + 43.75).toString(16).padStart(2, '0'));
        group.color = color;
        state.applied.color = color;
    }

    function applyGraphDesign(graph) {
        if (!graph) return;
        const graphs = new Set(), nodes = new Set();
        const visit = current => {
            if (!current || graphs.has(current)) return;
            graphs.add(current);
            for (const group of current._groups ?? []) applyGroupDesign(group);
            for (const node of current._nodes ?? []) {
                if (!nodes.has(node)) { nodes.add(node); applyNodeDesign(node); }
                if (node.subgraph) visit(node.subgraph);
            }
            for (const child of current.subgraphs?.values() ?? []) visit(child);
        };
        visit(graph.rootGraph ?? graph);
        graph.setDirtyCanvas?.(true, true);
    }

    function installGraphDesignHook(Graph, Group) {
        const prototype = Graph?.prototype;
        if (!scopeControls || !prototype?.add || !Group || decoratedGraphs.has(prototype)) return;
        decoratedGraphs.add(prototype);
        const original = prototype.add;
        prototype.add = function (item, ...args) {
            const result = original.call(this, item, ...args);
            if (item instanceof Group && item.graph === this) applyGroupDesign(item);
            else if (item?.graph === this && scopes.theme_regular_nodes) applyNodeDesign(item, true);
            return result;
        };
    }

    function installNodeDesignHooks(nodeTypes) {
        // Frontend-only nodes do not receive ComfyUI's server-node creation hook.
        // Decorate owned classes once, instead of watching graphs for additions.
        for (const [id, type] of Object.entries(nodeTypes ?? {})) {
            const prototype = type?.prototype;
            if (!id.endsWith(suffix) || !prototype || decoratedTypes.has(prototype)) continue;
            decoratedTypes.add(prototype);
            const original = prototype.onAdded;
            prototype.onAdded = function (...args) {
                const result = original?.apply(this, args);
                applyNodeDesign(this, true);
                return result;
            };
        }
    }

    function applyDesign(id, graph = app.graph) {
        if (!Object.hasOwn(designs, id)) throw Error('Unknown node design.');
        active = designs[id];
        const root = document.documentElement;
        for (const [key, value] of Object.entries({ ...active.tokens, 'node-bg': active.node.background })) {
            root.style.setProperty(`${prefix}${key}`, value);
        }
        root.dataset[dataset] = id;
        applyGraphDesign(graph);
        return onDesignApplied?.(id);
    }

    function applySaved() {
        if (Object.hasOwn(designs, saved)) return applyDesign(saved);
        if (Object.hasOwn(designs, defaultDesign)) applyDesign(defaultDesign);
        notice(`Theme “${saved}” is unavailable. Restore its JSON file or select another design. The saved selection has not been changed.`);
    }

    const options = () => {
        const choices = Object.entries(designs).sort(([a], [b]) => a === defaultDesign ? -1 : b === defaultDesign ? 1 : a.localeCompare(b))
            .map(([value, design]) => ({ text: design.label, value }));
        if (!Object.hasOwn(designs, saved)) choices.push({ text: `Unavailable: ${saved}`, value: saved });
        return choices;
    };
    async function showSaved(id = settingId, value = saved) {
        synchronizing = true;
        try { await app.ui.settings.setSettingValueAsync(id, value); }
        catch (error) { console.error(`[${category[0]}] Could not synchronize the design selector:`, error); }
        finally { synchronizing = false; }
    }
    async function readCatalog() {
        const response = await api.fetchApi(`${route}/themes`, { cache: 'no-store' });
        if (!response.ok) throw Error('Could not read theme files.');
        const catalog = await response.json();
        if (!catalog.themes || !Object.keys(catalog.themes).length) throw Error('No valid themes found. Restore the bundled themes folder.');
        designs = catalog.themes;
        if (catalog.errors?.length) notice(catalog.errors.join('\n'));
    }
    function reload() {
        // Serialize with saves so a reload cannot replace a newer user selection.
        pending = pending.then(async () => {
            try {
                await readCatalog();
                const definition = app.ui.settings.settingsLookup[settingId];
                definition.options = options();
                await applySaved();
                await showSaved();
            } catch (error) { notice(error.message); }
        });
        return pending;
    }
    async function initialize(config = {}) {
        saved = typeof config.node_design === 'string' ? config.node_design : defaultDesign;
        if (scopeControls) for (const key of Object.keys(scopes)) scopes[key] = config[key] === true;
        try { await readCatalog(); await applySaved(); }
        catch (error) { notice(error.message); }
        const settings = app.ui.settings;
        settings.addSetting({
            id: settingId, category: [...category, 'NodeDesign'], name: 'Node design',
            type: 'combo', defaultValue: saved, options: options(), sortOrder: 500,
            tooltip: 'Theme from this repo’s themes folder. Styles panel controls and untouched node defaults, including in subgraphs. Saved and custom title/background colors are preserved.',
            onChange(value) {
                if (!ready || synchronizing) return;
                if (!Object.hasOwn(designs, value)) return showSaved();
                const request = ++revision;
                pending = pending.then(async () => {
                    try {
                        const response = await api.fetchApi(`${route}/config/update`, {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ node_design: value }),
                        });
                        const result = await response.json();
                        if (!response.ok || !result.success) throw Error(result.error || 'Could not save node design.');
                        saved = value;
                        if (request === revision) await applyDesign(saved);
                    } catch (error) {
                        if (request === revision) {
                            await applySaved(); await showSaved();
                            notice(`Could not save the design: ${error.message}`);
                        }
                    }
                });
                return pending;
            },
        });
        if (scopeControls) {
            for (const [key, id, name, tooltip] of [
                ['theme_regular_nodes', 'RegularNodes', 'Theme regular nodes', 'Apply the theme to untouched defaults on other nodes too. Custom titles and backgrounds stay unchanged. Turning this off restores their previous colors.'],
                ['theme_groups', 'Groups', 'Theme groups', 'Match group colors to the selected design: RGB 60 with dark themes, RGB 80 with Neutral. Turning this off restores their previous colors.'],
            ]) {
                const scopeId = `${settingId}.${id}`;
                let scopeRevision = 0;
                settings.addSetting({
                    id: scopeId, category: [...category, id], name, tooltip,
                    type: 'boolean', defaultValue: scopes[key], sortOrder: 498,
                    onChange(value) {
                        if (!ready || synchronizing || typeof value !== 'boolean') return;
                        const request = ++scopeRevision;
                        pending = pending.then(async () => {
                            try {
                                const response = await api.fetchApi(`${route}/config/update`, {
                                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ [key]: value }),
                                });
                                const result = await response.json();
                                if (!response.ok || !result.success) throw Error(result.error || 'Could not save the setting.');
                                scopes[key] = value;
                                applyGraphDesign(app.graph);
                            } catch (error) {
                                if (request === scopeRevision) {
                                    await showSaved(scopeId, scopes[key]);
                                    notice(`Could not save ${name.toLowerCase()}: ${error.message}`);
                                }
                            }
                        });
                        return pending;
                    },
                });
                await showSaved(scopeId, scopes[key]);
            }
        }
        settings.addSetting({
            id: `${settingId}.Reload`, category: [...category, 'ReloadThemes'],
            name: 'Reload theme files', defaultValue: '', sortOrder: 499,
            tooltip: 'Read edits and new JSON files in this repo’s themes/custom folder, then reapply the selected theme.',
            type() {
                const button = document.createElement('button');
                button.className = 'comfy-menu-btn'; button.textContent = 'Reload themes';
                button.type = 'button';
                button.onclick = async () => {
                    button.disabled = true;
                    try { await reload(); } finally { button.disabled = false; }
                };
                return button;
            },
        });
        // The repo config wins over stale ComfyUI/browser settings on startup.
        await showSaved(); ready = true;
    }
    return { initialize, reload, applyDesign, applyNodeDesign, applyGraphDesign, installNodeDesignHooks, installGraphDesignHook };
}
