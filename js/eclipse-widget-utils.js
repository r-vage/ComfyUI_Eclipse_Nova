if (!document.getElementById('eclipse-tooltip-fix')) {
    const _s = document.createElement('style');
    _s.id = 'eclipse-tooltip-fix';
    _s.textContent = '.p-tooltip { pointer-events: none !important; }';
    document.head.appendChild(_s);
}

/** Shared widget state and renderer utilities. No global performance patches. */
export function debounce(fn, delay) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}
export function notifyVue(node) {
    const widgets = node.widgets;
    if (widgets?.length) {
        const last = widgets.pop();
        widgets.push(last);
    }
}
const _pendingNotify = new Set();
let _notifyScheduled = false;
export function batchedNotifyVue(node) {
    _pendingNotify.add(node);
    if (!_notifyScheduled) {
        _notifyScheduled = true;
        queueMicrotask(() => {
            _notifyScheduled = false;
            for (const n of _pendingNotify) notifyVue(n);
            _pendingNotify.clear();
        });
    }
}
const _pendingWidgetOptionRefresh = new Set();
let _widgetOptionRefreshScheduled = false;
export function batchedRefreshVueWidgetOptions(node) {
    _pendingWidgetOptionRefresh.add(node);
    if (_widgetOptionRefreshScheduled) return;
    _widgetOptionRefreshScheduled = true;
    queueMicrotask(() => {
        _widgetOptionRefreshScheduled = false;
        const nodes = [..._pendingWidgetOptionRefresh];
        _pendingWidgetOptionRefresh.clear();
        for (const n of nodes) {
            // Subgraph conversion preserves node IDs. Nodes 2.0 can therefore
            // reuse the original widget-store entry while the clone is being
            // attached, leaving its dynamic values provider bound to the node
            // that was removed from the parent graph. Rebind only that provider
            // to the attached widget and retain every other option/state field.
            for (const widget of n.widgets || []) {
                const stateOptions = widget?._state?.options;
                if (
                    widget?.type !== 'combo' ||
                    !stateOptions ||
                    !widget.options ||
                    stateOptions === widget.options
                ) continue;
                const liveOptions = widget.options;
                const liveValues = Object.getOwnPropertyDescriptor(liveOptions, 'values');
                if (!liveValues) continue;
                const registeredValues = Object.getOwnPropertyDescriptor(stateOptions, 'values');
                if (
                    registeredValues?.get === liveValues.get &&
                    registeredValues?.value === liveValues.value
                ) continue;
                const readLiveValues = liveValues.get
                    ? () => liveValues.get.call(liveOptions)
                    : () => liveValues.value;
                try {
                    Object.defineProperty(stateOptions, 'values', {
                        configurable: true,
                        enumerable: true,
                        get: readLiveValues,
                    });
                } catch (_) {}
            }
            batchedNotifyVue(n);
        }
    });
}
// Native ComfyUI load-state flag.  Frontend auto-wraps LGraph.configure()
// with a counter (dialogService bundle): configuringGraphLevel++/--.
// Reading window.app.configuringGraph is truthy whenever ANY graph (root
// or subgraph) is being configured, and automatically clears at the
// correct moment (end of configure finally block).  Supersedes the
// rAF-based auto-clear which could not span async server fetches.
export function isConfiguringGraph() {
    try {
        return !!(typeof window !== 'undefined' && window.app?.configuringGraph);
    } catch {
        return false;
    }
}

// Dynamic-input nodes need an explicit fit after adding/removing rows. Use the
// native node API once; layout ownership remains with the active renderer.
export function fitNodeToWidgets(node, { minHeight = 0, padding = 0 } = {}) {
    if (!node?.graph || node.flags?.collapsed || isConfiguringGraph()) return;
    const [width, height] = node.size;
    let measured;
    try {
        node.size[1] = 0;
        measured = node.computeSize()[1];
    } finally {
        node.size[1] = height;
    }
    if (Number.isFinite(measured)) {
        const nextHeight = Math.max(minHeight, measured) + padding;
        if (nextHeight !== height) node.setSize?.([width, nextHeight]);
    }
}

// Shared global vue-mode watcher — first repo to load installs the
// defineProperty on LiteGraph.vueNodesMode, subsequent repos piggyback
// on the shared callback set.  Prevents repos from overwriting each
// other's watcher regardless of load order.
const _VMC_KEY = '__comfy_vueModeCallbacks';
const _VMC_LOCK = '__comfy_vueModeWatcherInstalled';

function _installVueModeWatcher() {
    if (!window[_VMC_KEY]) window[_VMC_KEY] = new Set();
    if (window[_VMC_LOCK]) return;
    window[_VMC_LOCK] = true;
    try {
        let _value = !!LiteGraph.vueNodesMode;
        Object.defineProperty(LiteGraph, 'vueNodesMode', {
            get() { return _value; },
            set(v) {
                const prev = _value;
                _value = !!v;
                if (prev !== _value) {
                    for (const cb of (window[_VMC_KEY] || [])) {
                        try { cb(_value, prev); }
                        catch (e) { console.error('vueModeChange callback error', e); }
                    }
                }
            },
            configurable: true,
            enumerable: true,
        });
    } catch {}
}
export function isVueMode() {
    try {
        return !!LiteGraph.vueNodesMode;
    } catch {
        return false;
    }
}
export function onVueModeChange(callback) {
    _installVueModeWatcher();
    window[_VMC_KEY].add(callback);
    return () => window[_VMC_KEY].delete(callback);
}

// Delegate to one panel host so newly rendered textareas work without observers.
// ComfyUI checks this marker before forwarding DOM-wheel events to its canvas.
export function captureFocusedTextWheel(root) {
    let focused = null, previousCapture = null;
    const release = () => {
        if (!focused) return;
        if (previousCapture === null) focused.removeAttribute('data-capture-wheel');
        else focused.setAttribute('data-capture-wheel', previousCapture);
        focused = null;
    };
    const focus = event => {
        release();
        if (event.target.tagName !== 'TEXTAREA') return;
        focused = event.target;
        previousCapture = focused.getAttribute('data-capture-wheel');
        focused.setAttribute('data-capture-wheel', 'true');
    };
    const wheel = event => {
        if (event.target.tagName !== 'TEXTAREA' || root.ownerDocument.activeElement !== event.target) return;
        // Leave explicit zoom gestures to ComfyUI. Ordinary scrolling stays in
        // the focused field, including its edges; the browser scrolls the text.
        if (!event.ctrlKey && !event.metaKey) event.stopPropagation();
    };
    root.addEventListener('focusin', focus);
    root.addEventListener('focusout', release);
    root.addEventListener('wheel', wheel, { capture: true, passive: true });
    if (root.contains(root.ownerDocument.activeElement)) focus({ target: root.ownerDocument.activeElement });
    return () => {
        release();
        root.removeEventListener('focusin', focus);
        root.removeEventListener('focusout', release);
        root.removeEventListener('wheel', wheel, true);
    };
}

export function captureScrollableWheelInVue(element, { captureAtEdges = false } = {}) {
    let disposed = false;

    const releaseWheelCaptureForCanvas = () => {
        if (!isVueMode() || element.dataset.captureWheel !== 'true') return;
        element.removeAttribute('data-capture-wheel');
        queueMicrotask(() => {
            if (!disposed && isVueMode() && element.isConnected) {
                element.setAttribute('data-capture-wheel', 'true');
            }
        });
    };

    const handleWheel = (event) => {
        if (!isVueMode()) return;
        if (!captureAtEdges && element.scrollHeight <= element.clientHeight) {
            releaseWheelCaptureForCanvas();
            return;
        }

        const atTop = element.scrollTop <= 0;
        const atBottom = element.scrollTop + element.clientHeight >= element.scrollHeight - 1;
        if (!captureAtEdges && ((event.deltaY < 0 && atTop) || (event.deltaY > 0 && atBottom))) {
            releaseWheelCaptureForCanvas();
            return;
        }
        event.stopPropagation();
    };

    const focusOnPointerEnter = () => {
        if (isVueMode() && !element.contains(element.ownerDocument.activeElement)) element.focus({ preventScroll: true });
    };
    const syncRendererMode = () => {
        if (isVueMode()) {
            element.setAttribute('data-capture-wheel', 'true');
        } else {
            element.removeAttribute('data-capture-wheel');
        }
    };

    element.addEventListener('wheel', handleWheel);
    element.addEventListener('pointerenter', focusOnPointerEnter);
    syncRendererMode();
    const unsubscribe = onVueModeChange(syncRendererMode);

    return () => {
        if (disposed) return;
        disposed = true;
        unsubscribe();
        element.removeEventListener('wheel', handleWheel);
        element.removeEventListener('pointerenter', focusOnPointerEnter);
        element.removeAttribute('data-capture-wheel');
    };
}
