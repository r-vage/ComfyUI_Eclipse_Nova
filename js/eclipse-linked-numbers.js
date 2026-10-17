/** Resolve scalar primitives and transparent graph links for pre-execution previews. */
import { app } from './comfy/index.js';
import { findSetterByName, getLink, isSetterPathToRootActive } from './eclipse-set-get-utils.js';

// Resolve only numeric primitives and transparent graph routes. A widget on an
// arbitrary backend node is not evidence of that node's computed output.
export function numericInputValue(node, name) {
    let current = node;
    let input = current.inputs?.find(i => i.name === name || i.widget?.name === name);
    let widgetName = name;
    const visited = new Map();
    const hosts = [];
    const finite = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
    const hostFor = graph => {
        const entered = hosts.findLast(host => host.subgraph === graph);
        if (entered) return entered;
        const pending = [graph.rootGraph || app.graph];
        const seen = new Set();
        let found = null;
        let budget = 512;
        while (pending.length && budget > 0) {
            const outer = pending.pop();
            if (!outer || seen.has(outer)) continue;
            seen.add(outer);
            for (const candidate of outer._nodes || []) {
                if (--budget < 0) return null;
                if (candidate.subgraph === graph) {
                    if (found && found !== candidate) return null; // Ambiguous shared definition.
                    found = candidate;
                } else if (candidate.subgraph) pending.push(candidate.subgraph);
            }
        }
        return found;
    };
    for (let depth = 0; depth < 64; depth++) {
        if (input?.link == null) {
            const widget = current.widgets?.find(w =>
                (input?.widgetId && w.widgetId === input.widgetId)
                || w.name === (input?.widget?.name || widgetName));
            return finite(widget?.value);
        }
        const graph = current.graph;
        if (!graph) return null;
        const seen = visited.get(graph) || new Set();
        visited.set(graph, seen);
        if (seen.has(input.link)) return null;
        seen.add(input.link);
        const link = getLink(graph, input.link);
        if (!link) return null;
        if (link.origin_id === graph.inputNode?.id || link.originIsIoNode) {
            current = hostFor(graph);
            if (!current || current.mode === 2 || current.mode === 4) return null;
            input = current.inputs?.[link.origin_slot];
            widgetName = input?.name;
            if (!input) return null;
            continue;
        }
        const source = graph.getNodeById?.(link.origin_id);
        if (!source || source.mode === 2) return null;
        current = source;
        widgetName = undefined;
        if (source.mode === 4) {
            const type = source.outputs?.[link.origin_slot]?.type;
            const matches = i => i && LiteGraph.isValidConnection(i.type, type);
            input = matches(source.inputs?.[link.origin_slot]) ? source.inputs[link.origin_slot]
                : source.inputs?.find(i => i.type === type) || source.inputs?.find(matches);
        } else if (source.type === 'GetNode [Eclipse Nova]') {
            const setter = findSetterByName(graph, source.widgets?.[0]?.value);
            if (!setter || !isSetterPathToRootActive(setter.graph) || setter.node.mode === 2) return null;
            current = setter.node;
            input = current.inputs?.[link.origin_slot];
        } else if (source.type === 'Reroute' || source.type === 'SetNode [Eclipse Nova]') {
            input = source.inputs?.[0];
        } else if (source.subgraph) {
            hosts.push(source);
            const output = source.subgraph.outputNode?.slots?.[link.origin_slot];
            const innerLink = output?.getLinks?.()[0] || getLink(source.subgraph, output?.link);
            if (!innerLink) return null;
            current = { graph: source.subgraph };
            input = { link: innerLink.id };
        } else if (link.origin_slot === 0 && [
            'Float [Eclipse Nova]', 'PrimitiveFloat', 'PrimitiveInt', 'PrimitiveNode',
        ].includes(source.type)) {
            input = source.inputs?.find(i => i.name === 'value' || i.widget?.name === 'value');
            widgetName = 'value';
            continue;
        } else return null;
        // Transparent routes with no connected value require execution; they
        // must never borrow an unrelated local widget.
        if (input?.link == null) return null;
    }
    return null;
}

