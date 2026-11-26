/**
 * Find and select placed nodes in the active ComfyUI workflow.
 * SPDX-License-Identifier: Apache-2.0
 */
import { app, api } from './comfy/index.js';
import { button, element } from './eclipse-panel-controls.js';
import { findRootGraph, getGraphAncestors, getGraphDescendants } from './eclipse-set-get-utils.js';

const roles = {
    GetNode: 'getter', GetFirstNode: 'getter', GetAllActiveNode: 'getter',
    SetNode: 'setter', 'Mode Bridge Get': 'getter', 'Mode Bridge Set': 'setter',
};
let closeFinder;

function rootGraph() {
    return app.rootGraph ?? findRootGraph(app.canvas?.graph);
}

function describeNode(node, location) {
    const type = String(node.type ?? '');
    const base = type.replace(/\s*\[[^\]]+\]$/, '');
    const role = Object.hasOwn(roles, base) ? roles[base] : '';
    let variables = [];
    if (base === 'GetFirstNode' || base === 'GetAllActiveNode') {
        variables = (node.widgets ?? []).filter(w => /^var_\d+$/.test(w.name)).map(w => w.value);
    } else if (role) {
        variables = [node.properties?.bridgeName ?? node.widgets?.[0]?.value];
    }
    variables = variables.filter(v => typeof v === 'string' && v.trim());
    const displayType = node.subgraph ? 'Subgraph' : node.constructor?.nodeData?.display_name || node.constructor?.title || type;
    const title = node.title || displayType || String(node.id);
    const id = '#' + node.id;
    const exact = [id, String(node.id), title, type, displayType, ...variables].map(s => s.toLowerCase());
    const search = [title, type, displayType, id, location, role && role + 's', ...variables].join(' ').toLowerCase();
    const detail = [id, displayType !== title && displayType, ...variables.filter(v => !title.includes(v)), location]
        .filter(Boolean).join(' · ');
    return {
        node, title, detail, exact, search, role,
        key: `${node.graph.id}:${node.id}`,
        variables: variables.map(v => v.toLowerCase()),
    };
}

function entriesFor(graphs) {
    return graphs.flatMap((graph, i) => {
        const location = i === 0 ? 'Workflow' : getGraphAncestors(graph).reverse().slice(1)
            .map(g => g.name || 'Subgraph').join(' › ');
        return graph.nodes.map(node => describeNode(node, location));
    });
}

function matches(entries, query) {
    const terms = query.toLowerCase().match(/"[^"]*"|[^\s"]+/g) ?? [];
    if (!terms.length) return entries;
    const role = /^(getter|setter)s?$/.exec(terms[0])?.[1];
    if (role) terms.shift();
    const exact = [], partial = [];
    for (const entry of entries) {
        if (role && entry.role !== role) continue;
        if (!terms.every(term => {
            if (term.startsWith('"')) return (role ? entry.variables : entry.exact).includes(term.slice(1, -1));
            if (/^#\d+$/.test(term)) return term === '#' + entry.node.id;
            return entry.search.includes(term);
        })) continue;
        (terms.some(term => entry.exact.includes(term)) ? exact : partial).push(entry);
    }
    return exact.concat(partial);
}

export function toggleNodeFinder() {
    if (closeFinder) { closeFinder(); return; }
    if (!document.getElementById('eclipse-nova-find-node-style')) {
        const sheet = element('link');
        sheet.id = 'eclipse-nova-find-node-style';
        sheet.rel = 'stylesheet';
        sheet.href = new URL('./eclipse-workflow-find-node.css', import.meta.url).href;
        document.head.append(sheet);
    }
    const opener = document.activeElement;
    const panel = element('section', 'en-find-node');
    panel.popover = 'manual';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Find Node');
    const header = element('header');
    const close = button('×', 'Close Find Node', () => closeFinder());
    header.append(element('h2', '', 'Find Node'), close);
    const input = element('input');
    input.type = 'search';
    input.placeholder = 'Name, type, ID or variable';
    input.title = 'Use getter "name" or setter "name" to find an exact variable.';
    input.setAttribute('aria-label', 'Search workflow nodes');
    input.autocomplete = 'off';
    input.spellcheck = false;
    const list = element('ul');
    list.setAttribute('aria-label', 'Matching nodes');
    const status = element('div', 'en-find-status');
    status.setAttribute('role', 'status');
    panel.append(header, input, status, list);
    document.body.append(panel);

    const events = new AbortController();
    let graphEvents = new AbortController();
    let refreshFrame = 0, jumpSequence = 0;
    let entries = [];
    const attached = (root, graph, node) => root === rootGraph() && graph?.getNodeById(node.id) === node
        && (graph === root || getGraphDescendants(root).includes(graph));

    async function jump(node) {
        const root = rootGraph(), graph = node.graph, canvas = app.canvas;
        const sequence = ++jumpSequence;
        if (!canvas || !attached(root, graph, node)) { refresh(); return; }
        if (canvas.graph !== graph) {
            canvas.setGraph(graph);
            // Subgraph navigation restores its viewport on the next frame.
            await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        }
        if (sequence !== jumpSequence || canvas.graph !== graph || !attached(root, graph, node)) return;
        canvas.selectItems([node]);
        if (node.boundingRect.every(value => value === 0)) node.updateArea();
        canvas.animateToBounds(node.boundingRect);
        canvas.canvas.focus({ preventScroll: true });
    }

    function draw() {
        const selected = document.activeElement;
        const focused = list.contains(selected) ? selected.dataset.nodeKey : null;
        const rows = matches(entries, input.value);
        const fragment = document.createDocumentFragment();
        let restoreFocus;
        for (const { node, title, detail, key } of rows) {
            const item = element('li');
            const target = button('', `Jump to ${title} · ${detail}`, () => jump(node));
            target.dataset.nodeKey = key;
            if (key === focused) restoreFocus = target;
            const labels = element('span', 'en-find-labels');
            labels.append(element('strong', '', title), element('small', '', detail));
            target.append(labels, element('span', 'en-find-jump', 'Jump'));
            item.append(target);
            fragment.append(item);
        }
        list.replaceChildren(fragment);
        status.textContent = rows.length ? `${rows.length} ${rows.length === 1 ? 'node' : 'nodes'}` : 'No matching nodes';
        if (focused) (restoreFocus ?? input).focus({ preventScroll: true });
    }

    function refresh() {
        const root = rootGraph();
        const graphs = root ? [root, ...getGraphDescendants(root)] : [];
        graphEvents.abort();
        graphEvents = new AbortController();
        for (const graph of graphs) {
            for (const event of ['node:added', 'node:removed', 'configured'])
                graph.events?.addEventListener(event, scheduleRefresh, { signal: graphEvents.signal });
        }
        entries = entriesFor(graphs);
        draw();
    }
    function scheduleRefresh() {
        if (!refreshFrame) refreshFrame = requestAnimationFrame(() => { refreshFrame = 0; refresh(); });
    }
    closeFinder = () => {
        ++jumpSequence;
        events.abort();
        graphEvents.abort();
        cancelAnimationFrame(refreshFrame);
        panel.remove();
        closeFinder = undefined;
        if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
    input.oninput = () => { list.scrollTop = 0; draw(); };
    input.onfocus = scheduleRefresh;
    panel.onkeydown = event => {
        event.stopPropagation();
        if (event.isComposing) return;
        if (event.key === 'Escape') { event.preventDefault(); closeFinder(); return; }
        const current = event.target.closest('li');
        if (event.key === 'Enter' && event.target === input) {
            event.preventDefault();
            list.querySelector('button')?.click();
        } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            const next = event.key === 'ArrowDown' ? (current ? current.nextElementSibling : list.firstElementChild)
                : current?.previousElementSibling;
            (next?.firstElementChild ?? (current && event.key === 'ArrowUp' ? input : event.target)).focus();
        }
    };
    api.addEventListener('graphChanged', scheduleRefresh, { signal: events.signal });
    const canvasElement = app.canvas?.canvas;
    canvasElement?.addEventListener('litegraph:set-graph', scheduleRefresh, { signal: events.signal });
    canvasElement?.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !event.isComposing) closeFinder();
    }, { signal: events.signal });
    refresh();
    panel.showPopover();
    input.focus();
}
