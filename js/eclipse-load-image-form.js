/** Image browser, upload/drop/paste and a direct preview inside one panel. */
import { app, api } from './comfy/index.js';
import { element, button } from './eclipse-panel-controls.js';
import { createEclipseImageBrowser, chooseAdjacentImage, invalidateImageBrowserThumbnail, invalidateImageBrowserThumbnailSource } from './eclipse-image-browser.js';
import { imageFiles, imageURL, imageParams, postJSON } from './eclipse-image-loader-api.js';
import { onVueModeChange } from './eclipse-widget-utils.js';
import { METADATA_GROUPS } from './eclipse-image-loader-state.js';

const GROUP_LABELS = { sampler: 'Sampler settings', positive: 'Positive prompt', negative: 'Negative prompt', seed: 'Seed' };

export class LoadImageForm {
    constructor(controller) {
        this.controller = controller; this.lists = {}; this.request = 0; this.status = '';
        this.browser = createEclipseImageBrowser({
            source: this.config.source, selected: this.filename(), popoverClass: 'en-image-picker',
            buildThumbnailURL: (file, source) => '/eclipse-nova/load_image/thumbnail?' + new URLSearchParams(imageParams(file, source)),
            fetchThumbnail: url => api.fetchApi(url, { cache: 'no-store' }),
            onSourceChange: async source => { this.controller.edit(state => { state.config.source = source; }); await this.loadList(source); },
            onSelect: (file, source) => this.controller.edit(state => { state.config.files[source] = file; }),
            onUpload: files => this.upload(files), onRefresh: source => this.refresh(source), onDelete: (file, source) => this.remove(file, source),
        });
        this.image = element('img'); this.image.alt = 'Selected image'; this.image.draggable = false;
        this.image.onload = () => { this.status = `${this.image.naturalWidth} × ${this.image.naturalHeight}`; this.syncSummaries(); this.controller.measure(); };
        this.image.onerror = () => { this.status = 'Selected image is missing or cannot be previewed.'; this.syncSummaries(); };
        this.image.oncontextmenu = event => this.openImageMenu(event);
        this.unsubscribe = onVueModeChange(() => { this.browser.close(); this.closeImageMenu(); });
        this.events = new AbortController();
        document.addEventListener('paste', event => {
            if (!app.canvas?.selected_nodes?.[controller.node.id] || /INPUT|TEXTAREA/.test(event.target?.tagName)) return;
            const files = [...(event.clipboardData?.files ?? [])];
            if (files.length) { event.preventDefault(); void this.upload(files); }
        }, { signal: this.events.signal });
    }
    get config() { return this.controller.state.config; }
    filename() { return this.config.files[this.config.source]; }
    openImageMenu(event) {
        event.preventDefault(); event.stopPropagation(); this.closeImageMenu();
        // An unregistered editor target lets ComfyUI's Mask Editor return a file
        // without attaching its native preview or extra widgets to the real node.
        const form = this, node = this.controller.node, target = Object.create(node);
        Object.assign(target, { imgs: [this.image],
            images: [imageParams(this.filename(), this.config.source)], imageIndex: 0, properties: {}, onWidgetChanged() {} });
        const widget = { name: 'image', type: 'combo', get value() { return `${form.filename()} [${form.config.source}]`; },
            set value(value) {
                queueMicrotask(() => app.extensionManager._p._s.get('nodeOutput').removeNodeOutputsForNode(target));
                if (form.dead || typeof value !== 'string') return;
                const source = value.endsWith(' [output]') ? 'output' : 'input', file = value.replace(/ \[(input|output|temp)\]$/, '');
                form.controller.edit(state => { state.config.source = source; state.config.files[source] = file; });
                void form.loadList(source, true);
            } };
        Object.defineProperties(target, {
            id: { value: `eclipse-image-editor-${crypto.randomUUID()}`, writable: true, configurable: true },
            widgets: { value: [widget], writable: true, configurable: true },
        });
        const entries = []; node.getExtraMenuOptions?.call(target, app.canvas, entries);
        const menu = this.imageMenu = element('div', 'en-panel-menu'); menu.setAttribute('role', 'menu'); menu.setAttribute('aria-label', 'Image actions');
        for (const entry of entries.filter(item => ['Open Image', 'Save Image'].includes(item?.content) || item?.content?.includes('MaskEditor'))) {
            const item = button(entry.content, entry.content, () => { this.closeImageMenu(); entry.callback(); }); item.setAttribute('role', 'menuitem'); menu.append(item);
        }
        document.body.append(menu); menu.style.left = `${Math.max(4, Math.min(event.clientX, innerWidth - menu.offsetWidth - 4))}px`;
        menu.style.top = `${Math.max(4, Math.min(event.clientY, innerHeight - menu.offsetHeight - 4))}px`;
        this.menuEvents = new AbortController();
        document.addEventListener('pointerdown', event => { if (!menu.contains(event.target)) this.closeImageMenu(); }, { capture: true, signal: this.menuEvents.signal });
        document.addEventListener('keydown', event => { if (event.key === 'Escape') this.closeImageMenu(); }, { capture: true, signal: this.menuEvents.signal });
    }
    closeImageMenu() { this.menuEvents?.abort(); this.imageMenu?.remove(); this.imageMenu = null; }
    async loadList(source, refresh = false) {
        const request = ++this.request;
        try {
            const files = await imageFiles(source, refresh);
            if (this.dead || request !== this.request) return;
            this.lists[source] = files;
            if (this.config.source === source) {
                if (!this.config.files[source] && files.length) this.controller.edit(state => { state.config.files[source] = files[0]; });
                this.browser.setFiles(files, this.config.files[source]); this.syncSummaries();
            }
        } catch (error) { if (!this.dead && request === this.request) { this.status = error.message; this.syncSummaries(); } }
    }
    async refresh(source) {
        invalidateImageBrowserThumbnailSource(source); await this.loadList(source, true);
        if (!this.dead) { this.previewKey = ''; this.metadataKey = null; this.render(); }
        return { message: this.status || `Refreshed ${this.lists[source]?.length ?? 0} images` };
    }
    async remove(file, source) {
        if (!confirm(`Delete "${file}"?`)) return { success: false, cancelled: true };
        try {
            const old = this.lists[source] ?? [], index = old.indexOf(file);
            await postJSON('/eclipse-nova/load_image/delete', { filename: file, folder: source });
            invalidateImageBrowserThumbnail(file, source);
            const files = await imageFiles(source, true); if (this.dead) return { success: true };
            this.lists[source] = files;
            this.controller.edit(state => { if (state.config.files[source] === file) state.config.files[source] = chooseAdjacentImage(files, index); });
            return { success: true, message: `Deleted ${file}` };
        } catch (error) { return { success: false, message: error.message }; }
    }
    async upload(files) {
        const accepted = [...files].filter(file => file.type.startsWith('image/') || /\.(png|jpe?g|webp|bmp|gif|tiff?)$/i.test(file.name));
        if (!accepted.length) return { success: false, errors: ['No supported images'] };
        try {
            const body = new FormData(); for (const file of accepted) body.append('images', file, file.name);
            const response = await api.fetchApi('/eclipse-nova/load_image/upload', { method: 'POST', body });
            const result = await response.json(); if (!response.ok) throw Error(result.error ?? 'Upload failed.');
            if (result.files?.length && !this.dead) {
                this.lists.input = await imageFiles('input', true); if (this.dead) return result;
                this.controller.edit(state => { state.config.source = 'input'; state.config.files.input = result.files.at(-1); });
            }
            return { ...result, message: result.errors?.join('; ') || `Uploaded ${result.files?.length ?? 0} images` };
        } catch (error) { this.status = error.message; this.syncSummaries(); return { success: false, errors: [error.message], message: error.message }; }
    }
    render() {
        const content = element('div', 'en-panel-content');
        this.browser.setSource(this.config.source); this.browser.setFiles(this.lists[this.config.source] ?? [], this.filename());
        content.append(this.browser.element);
        const actions = element('div', 'en-loader-actions'), bar = element('div', 'en-panel-bar en-loader-metadata');
        const toggle = button('Metadata', 'Metadata', () => this.controller.edit(state => { state.config.metadata = !state.config.metadata; }));
        toggle.title = 'Choose which generation settings and prompts to include in the pipe.'; toggle.setAttribute('aria-pressed', String(this.config.metadata)); bar.append(toggle);
        actions.append(element('span', 'en-panel-note', 'Drop an image on the preview'), bar); content.append(actions);
        this.metadataSection = element('div', 'en-loader-generation');
        if (this.config.metadata) content.append(this.metadataSection);
        this.syncMetadata();
        const preview = element('div', 'en-loader-preview');
        if (this.filename()) {
            const key = `${this.config.source}/${this.filename()}`;
            if (this.previewKey !== key) { this.previewKey = key; this.status = ''; this.image.src = imageURL(this.filename(), this.config.source) + `&cb=${Date.now()}`; }
            preview.append(this.image);
        } else { preview.append(element('span', 'en-panel-note', 'Select or upload an image.')); this.previewKey = ''; this.image.removeAttribute('src'); }
        preview.ondragover = event => { event.preventDefault(); event.stopPropagation(); };
        preview.ondrop = event => { event.preventDefault(); event.stopPropagation(); void this.upload(event.dataTransfer.files); };
        content.append(preview);
        this.statusElement = element('div', 'en-panel-note'); this.statusElement.setAttribute('role', 'status'); content.append(this.statusElement);
        this.controller.root.replaceChildren(content); this.syncSummaries(); this.controller.measure();
        if (!this.lists[this.config.source] && this.loadingSource !== this.config.source) {
            this.loadingSource = this.config.source; void this.loadList(this.config.source);
        }
    }
    syncSummaries() {
        if (!this.statusElement) return;
        const missing = this.filename() && this.lists[this.config.source] && !this.lists[this.config.source].includes(this.filename());
        this.statusElement.textContent = missing ? `${this.filename()} (missing)` : this.status;
        this.statusElement.title = this.statusElement.textContent;
    }
    syncMetadata() {
        const key = this.config.metadata && this.filename() ? `${this.config.source}/${this.filename()}` : '';
        if (this.metadataKey !== key) {
            this.metadataKey = key; this.metadataValues = null; this.metadataError = '';
            this.metadataAbort?.abort(); this.metadataAbort = new AbortController();
            if (key) void this.readMetadata(key, this.metadataAbort.signal);
        }
        this.renderMetadata();
    }
    async readMetadata(key, signal) {
        try {
            const query = new URLSearchParams(imageParams(this.filename(), this.config.source));
            const response = await api.fetchApi('/eclipse-nova/load_image/metadata?' + query, { cache: 'no-store', signal });
            const data = await response.json();
            if (!response.ok) throw Error(data.error ?? 'Unable to read generation settings.');
            if (this.dead || signal.aborted || this.metadataKey !== key) return;
            this.metadataValues = data.values ?? {};
        } catch (error) {
            if (this.dead || signal.aborted || this.metadataKey !== key) return;
            this.metadataError = error.message;
        }
        this.renderMetadata(); this.controller.measure();
    }
    renderMetadata() {
        if (!this.metadataSection || !this.config.metadata) return;
        const state = this.controller.state, values = this.metadataValues ?? {};
        const available = key => METADATA_GROUPS[key].some(field => Object.hasOwn(values, field));
        const section = element('section', 'en-panel-section'); section.setAttribute('aria-label', 'Generation settings');
        const open = state.sectionOpen('generation'), header = element('div', 'en-panel-section-header');
        const toggle = button('', 'Generation settings', () => this.controller.edit(state => state.toggleSection('generation')));
        toggle.className = 'en-panel-section-toggle'; toggle.setAttribute('aria-expanded', String(open));
        const selected = Object.keys(GROUP_LABELS).filter(key => this.config.metadata_fields[key] && available(key));
        toggle.append(element('span', 'en-panel-section-label', `${open ? '▾' : '▸'} Generation settings`),
            element('span', 'en-panel-summary', selected.map(key => ({ sampler: 'Sampler', positive: 'Positive', negative: 'Negative', seed: 'Seed' })[key]).join(' · ') || 'None'));
        header.append(toggle); section.append(header);
        if (open) {
            const body = element('div', 'en-panel-section-body');
            if (!this.metadataValues) {
                body.append(element('div', 'en-panel-note', this.metadataError || (this.filename() ? 'Reading generation settings…' : 'Select an image to read its generation settings.')));
            } else {
                for (const [key, title] of Object.entries(GROUP_LABELS)) {
                    const row = element('div', 'en-loader-metadata-row'), label = element('label', 'en-loader-metadata-toggle');
                    row.dataset.group = key;
                    const check = element('input'); check.type = 'checkbox'; check.checked = available(key) && this.config.metadata_fields[key];
                    check.disabled = !available(key); check.setAttribute('aria-label', `Include ${title.toLowerCase()}`);
                    check.onchange = () => this.controller.edit(state => { state.config.metadata_fields[key] = check.checked; });
                    label.append(check, element('span', '', title)); row.append(label);
                    if (!available(key)) row.append(element('span', 'en-panel-note', 'Not available'));
                    else if (key === 'positive' || key === 'negative') {
                        const text = values[METADATA_GROUPS[key][0]], display = element('textarea');
                        display.readOnly = true; display.rows = 2; display.value = text;
                        display.placeholder = 'Empty prompt'; display.setAttribute('aria-label', title);
                        row.append(display);
                    } else {
                        const display = key === 'seed' ? String(values.seed) : [
                            values.sampler_name, values.scheduler,
                            Object.hasOwn(values, 'steps') ? `${values.steps} steps` : null,
                            Object.hasOwn(values, 'cfg') ? `CFG ${values.cfg}` : null,
                        ].filter(value => value != null).join(' · ');
                        row.append(element('div', 'en-loader-metadata-value', display));
                    }
                    body.append(row);
                }
                if (!Object.keys(values).length) body.prepend(element('div', 'en-panel-note', 'No generation settings found in this image.'));
            }
            section.append(body);
        }
        this.metadataSection.replaceChildren(section);
    }
    dispose() { this.browser.close(); this.closeImageMenu(); }
    destroy() { this.dead = true; this.request++; this.metadataAbort?.abort(); this.events.abort(); this.unsubscribe(); this.browser.destroy(); this.image.onload = this.image.onerror = null; }
}
