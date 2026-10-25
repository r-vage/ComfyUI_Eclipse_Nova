/** Full-resolution Image Selector actions without loading originals into its grid. */
import { app, api } from './comfy/index.js';
import { markEclipseContextMenuOwner } from './eclipse-context-menu-ownership.js';
import { showEclipseToast } from './eclipse-notifications.js';

const isImageAction = entry => ['Open Image', 'Copy Image', 'Save Image', 'Copy (Clipspace)'].includes(entry?.content)
    || /^Open in Mask\s?Editor/.test(entry?.content || '');

export class SelectorImageActions {
    constructor(node, firstImage) { this.node = node; this.selected = firstImage; }

    bind(element, getImage) {
        markEclipseContextMenuOwner(element);
        element.addEventListener('pointerenter', () => { this.selected = getImage(); });
        element.addEventListener('contextmenu', event => {
            event.preventDefault(); event.stopPropagation();
            this.selected = getImage(); this.close();
            const entries = [];
            this.node.getExtraMenuOptions?.(app.canvas, entries);
            const actions = entries.filter(isImageAction);
            if (!actions.length) return;
            this.menu = new LiteGraph.ContextMenu(actions, { event });
            const menu = this.menu, close = menu.close;
            menu.close = (...args) => {
                if (this.menu === menu) this.menu = null;
                return close.apply(menu, args);
            };
            this.menu.root?.setAttribute('role', 'menu');
            this.menu.root?.setAttribute('aria-label', 'Image actions');
        });
    }

    options(originalMenu, canvas, options) {
        if (!this.selected) return originalMenu?.call(this.node, canvas, options);
        const data = this.selected.original || this.selected;
        const image = new Image();
        image.src = api.apiURL(`/view?${new URLSearchParams({
            filename: data.filename, subfolder: data.subfolder || '', type: data.type || 'temp',
        })}`);
        // Native actions capture this target. Never attach the full image to the
        // real node, where ComfyUI could create another preview or resize it.
        const target = Object.create(this.node);
        for (const [key, value] of Object.entries({ imgs: [image], images: [data], imageIndex: 0, overIndex: 0 })) {
            Object.defineProperty(target, key, { value, writable: true, configurable: true });
        }
        const entries = [];
        const result = originalMenu?.call(target, canvas, entries);
        for (const entry of entries) {
            if (!isImageAction(entry) || typeof entry.callback !== 'function') continue;
            // Open/save stay synchronous for browser popup/download permission.
            // Canvas copying, Clipspace and the mask editor need decoded pixels.
            const callback = entry.callback;
            if (['Open Image', 'Save Image'].includes(entry.content)) {
                entry.callback = (...args) => callback.apply(target, args);
                continue;
            }
            entry.callback = async (...args) => {
                try {
                    await image.decode();
                    if (this.disposed) return;
                    const result = await callback.apply(target, args);
                    // New frontends read Clipspace descriptors from their output
                    // store, whose native images this DOM-only node suppresses.
                    const clipspace = app.constructor.clipspace;
                    if (entry.content === 'Copy (Clipspace)' && clipspace?.imgs?.[0]?.src === image.src) {
                        clipspace.images = [data];
                    }
                    return result;
                }
                catch (error) {
                    showEclipseToast('Eclipse Nova Image Selector', `Could not load the original image: ${error.message || error}`);
                }
            };
        }
        options.push(...entries);
        return result;
    }

    close() { this.menu?.close(); this.menu = null; }
    dispose() { this.disposed = true; this.close(); this.selected = null; }
}
