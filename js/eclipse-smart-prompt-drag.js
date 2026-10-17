/** Pointer reordering confined to one Smart Prompt folder, committed on drop. */
export class PromptRowDrag {
    start(event, row, commit) {
        if (event.button !== 0 || !event.isPrimary) return;
        this.cancel();
        const handle = event.currentTarget, parent = row.parentElement, rows = [...parent.children];
        if (rows.length < 2) return;
        event.preventDefault(); event.stopPropagation();
        const from = rows.indexOf(row), bounds = parent.getBoundingClientRect();
        const others = rows.filter(item => item !== row).map(item => ({ item, rect: item.getBoundingClientRect() }));
        const events = new AbortController(), options = { signal: events.signal, capture: true };
        let dragging = false, delta = 0, marker = null;
        const clearMarker = () => { if (marker) delete marker.dataset.dropEdge; marker = null; };
        this.cleanup = () => {
            events.abort(); clearMarker(); delete row.dataset.dragging;
            if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
        };
        const move = next => {
            if (next.pointerId !== event.pointerId) return;
            next.preventDefault(); next.stopPropagation();
            // A refresh, resize or renderer change invalidates the measured row positions.
            const current = parent.getBoundingClientRect();
            if (!row.isConnected || ['x', 'y', 'width', 'height'].some(key => Math.abs(current[key] - bounds[key]) > 1)) { this.cancel(); return; }
            if (!dragging && Math.hypot(next.clientX - event.clientX, next.clientY - event.clientY) < 4) return;
            dragging = true; row.dataset.dragging = 'true'; clearMarker(); delta = 0;
            if (next.clientX < bounds.left || next.clientX > bounds.right || next.clientY < bounds.top || next.clientY > bounds.bottom) return;
            const before = others.findIndex(({ rect }) => next.clientY < rect.top + rect.height / 2);
            const to = before < 0 ? others.length : before;
            delta = to - from;
            if (delta) {
                marker = others[Math.min(to, others.length - 1)].item;
                marker.dataset.dropEdge = before < 0 ? 'after' : 'before';
            }
        };
        handle.addEventListener('pointermove', move, options);
        handle.addEventListener('pointerup', next => {
            if (next.pointerId !== event.pointerId) return;
            move(next);
            const changed = !!this.cleanup && dragging && delta !== 0;
            this.cancel();
            if (changed) commit(delta);
        }, options);
        const cancel = () => this.cancel();
        handle.addEventListener('pointercancel', cancel, options);
        handle.addEventListener('lostpointercapture', cancel, options);
        window.addEventListener('blur', cancel, options);
        window.addEventListener('resize', cancel, options);
        window.addEventListener('wheel', cancel, { ...options, passive: true });
        window.addEventListener('keydown', key => {
            if (key.key === 'Escape') { key.preventDefault(); key.stopPropagation(); this.cancel(); }
        }, options);
        handle.setPointerCapture(event.pointerId);
    }
    cancel() { const cleanup = this.cleanup; this.cleanup = null; cleanup?.(); }
}
