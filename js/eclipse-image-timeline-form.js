/** Image slot editor and preview. Copyright (c) 2026 r-vage. Apache-2.0. */
import { api } from './comfy/index.js';
import { button, element } from './eclipse-panel-controls.js';
import { runActions } from './eclipse-panel-run.js';
import { createEclipseImageBrowser, invalidateImageBrowserThumbnailSource } from './eclipse-image-browser.js';
import { imageFiles, imageURL, imageParams } from './eclipse-image-loader-api.js';
import { captureScrollableWheelInVue, onVueModeChange } from './eclipse-widget-utils.js';
import { GROUPS, LABELS } from './eclipse-image-timeline-state.js';

const title = value => value === 'inherit' ? 'Use timeline setting' : value.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
const fileKey = file => file ? `${file.source}/${file.filename}` : '';

export class ImageTimelineForm {
    constructor(controller) {
        this.controller = controller; this.views = new Map(); this.lists = {}; this.sizes = new Map(); this.request = 0;
        this.source = 'input'; this.events = new AbortController();
        this.content = element('div', 'en-panel-content');
        this.canvas = element('div', 'en-panel-grid'); this.canvas.setAttribute('aria-label', 'Canvas size');
        this.canvasInputs = {};
        for (const key of ['width', 'height']) {
            const label = element('label', 'en-panel-field'), input = this.canvasInputs[key] = element('input');
            label.append(element('span', '', title(key))); input.type = 'number'; input.min = '0'; input.max = '8192'; input.step = '1';
            input.setAttribute('aria-label', `Canvas ${key}`); input.title = `0 = derive from the first enabled image. A non-empty ${key} input overrides this local value.`;
            input.oninput = () => { if (input.value !== '' && input.checkValidity()) this.edit(state => { state.config[key] = input.valueAsNumber; }); };
            input.onchange = () => { input.value = this.config[key]; }; label.append(input); this.canvas.append(label);
        }
        this.canvasNote = element('div', 'en-panel-note');
        const previewActions = element('div', 'eit-preview-actions');
        this.updateActions = runActions(controller, {
            playText: 'Update previews', playLabel: 'Update image previews',
            runLocally: () => {
                if (this.hasDimensionInputs()) return false;
                this.refreshPreviews();
                return true;
            },
            beforeRun: () => this.refreshPreviews(),
        });
        previewActions.append(this.canvasNote, this.updateActions);
        const columns = element('div', 'eit-columns'), left = element('section', 'eit-left'); left.setAttribute('aria-label', 'Image slots');
        left.append(element('div', 'en-panel-note', 'Images · drop files to add · drag handles to reorder'));
        this.list = element('div', 'eit-list'); this.list.setAttribute('aria-label', 'Ordered images');
        // Vue needs a focused scroll host before its ancestor wheel handler runs.
        this.list.tabIndex = -1;
        this.releaseScroll = captureScrollableWheelInVue(this.list, { captureAtEdges: true });
        this.list.ondragover = event => {
            if ([...(event.dataTransfer?.types ?? [])].includes('Files')) {
                event.preventDefault(); event.stopPropagation(); this.list.classList.add('eit-file-drop');
            }
        };
        this.list.ondragleave = event => { if (!this.list.contains(event.relatedTarget)) this.list.classList.remove('eit-file-drop'); };
        this.list.ondrop = event => {
            this.list.classList.remove('eit-file-drop');
            if (event.dataTransfer.files.length) { event.preventDefault(); event.stopPropagation(); void this.upload(event.dataTransfer.files, { append: true }); }
        };
        const footer = element('div', 'eit-footer'); this.count = element('span', 'en-panel-note');
        this.add = button('+ Image', 'Add image slot', () => { this.edit(state => state.add()); this.list.lastElementChild?.scrollIntoView({ block: 'nearest' }); });
        footer.append(this.add, this.count); left.append(this.list, footer, element('div', 'en-panel-note', 'Each blend leads into the next enabled image. Empty slots are ignored.'));
        const right = element('section', 'eit-right'); right.setAttribute('aria-label', 'Selected image');
        this.browser = createEclipseImageBrowser({
            source: this.source, popoverClass: 'en-image-picker',
            buildThumbnailURL: (file, source) => '/eclipse-nova/load_image/thumbnail?' + new URLSearchParams(imageParams(file, source)),
            fetchThumbnail: url => api.fetchApi(url, { cache: 'no-store' }),
            onSourceChange: source => { this.source = source; return this.loadList(source); },
            onSelect: (filename, source) => {
                this.edit(state => { const row = state.active() ?? state.add(); if (row) state.update(row.id, { file: { filename, source } }); });
            },
            onRefresh: source => this.refresh(source), onUpload: files => this.upload(files),
        });
        this.browser.element.addEventListener('click', () => { if (!this.lists[this.source]) void this.loadList(this.source); }, { capture: true, signal: this.events.signal });
        this.frame = element('div', 'eit-preview'); this.picture = element('div', 'eit-picture');
        this.image = element('img'); this.image.alt = 'Timeline image preview'; this.image.draggable = false;
        this.image.onload = () => { this.sizes.set(this.previewKey, [this.image.naturalWidth, this.image.naturalHeight]); this.previewSize(); };
        this.image.onerror = () => { this.status.textContent = 'Image unavailable. Choose another file or refresh the list.'; };
        this.empty = element('span', 'en-panel-note', 'Add an image slot, then choose or drop a file.');
        this.picture.append(this.image); this.frame.append(this.picture, this.empty);
        this.frame.ondragover = event => { if ([...(event.dataTransfer?.types ?? [])].includes('Files')) { event.preventDefault(); event.stopPropagation(); } };
        this.frame.ondrop = event => { if (event.dataTransfer.files.length) { event.preventDefault(); event.stopPropagation(); void this.upload(event.dataTransfer.files); } };
        this.status = element('div', 'en-panel-note'); this.status.setAttribute('role', 'status');
        this.meta = element('section', 'eit-metadata en-panel-section'); this.meta.setAttribute('aria-label', 'Image metadata');
        right.append(this.browser.element, this.frame, this.status, this.meta); columns.append(left, right);
        this.content.append(this.canvas, previewActions, columns);
        this.resize = new ResizeObserver(() => this.previewSize()); this.resize.observe(this.frame);
        this.unsubscribe = onVueModeChange(() => this.browser.close());
        this.content.addEventListener('wheel', event => event.stopPropagation(), { passive: true });
    }
    get state() { return this.controller.state; }
    get config() { return this.state.config; }
    edit(action) { this.controller.edit(action, false); }
    update(id, values) {
        const framing = ['fit', 'crop_x', 'crop_y'].some(key => Object.hasOwn(values, key));
        this.edit(state => {
            state.update(id, values);
            if (framing) state.editor.activeId = id;
        });
    }
    dimensionLink(key) { return this.controller.node.inputs?.find(input => input.name === key)?.link ?? null; }
    hasDimensionInputs() { return ['width', 'height'].some(key => this.dimensionLink(key) !== null); }
    refreshPreviews() {
        this.previewKey = ''; this.sizeKey = null; this.sizes.clear(); this.syncSummaries();
        if (!this.hasDimensionInputs()) this.status.textContent = 'Previews updated locally. No workflow queued.';
    }
    async loadList(source, refresh = false) {
        const request = ++this.request;
        try {
            const files = await imageFiles(source, refresh);
            if (this.dead || request !== this.request) return;
            this.lists[source] = files;
            if (this.source === source) this.browser.setFiles(files, this.state.active()?.file?.source === source ? this.state.active().file.filename : '');
        } catch (error) { if (!this.dead && request === this.request) this.browser.setStatus(error.message, true); }
    }
    async refresh(source) {
        invalidateImageBrowserThumbnailSource(source); await this.loadList(source, true);
        if (this.dead) return;
        this.previewKey = ''; this.metadataKey = null; this.sizeKey = null; this.sizes.clear(); this.syncSummaries();
        return { message: `Refreshed ${this.lists[source]?.length ?? 0} images` };
    }
    async upload(files, { append = false } = {}) {
        const accepted = [...files].filter(file => file.type.startsWith('image/') || /\.(png|jpe?g|webp|bmp|gif|tiff?)$/i.test(file.name));
        const id = append ? null : this.state.active()?.id, epoch = this.epoch;
        if (!accepted.length) return { errors: ['No supported images'] };
        try {
            const body = new FormData(); for (const file of accepted) body.append('images', file, file.name);
            const response = await api.fetchApi('/eclipse-nova/load_image/upload', { method: 'POST', body, signal: this.events.signal });
            const result = await response.json(); if (!response.ok) throw Error(result.error ?? 'Upload failed.');
            if (this.dead || epoch !== this.epoch) return result;
            const loaded = result.files ?? [];
            this.edit(state => {
                for (const [index, filename] of loaded.entries()) {
                    const row = index === 0 && id ? state.config.images.find(row => row.id === id) : null;
                    if (row) state.update(id, { file: { source: 'input', filename } });
                    else state.add({ source: 'input', filename });
                }
            });
            this.source = 'input'; this.browser.setSource(this.source); await this.loadList('input', true);
            return { ...result, message: result.errors?.join('; ') || `Uploaded ${loaded.length} images. Slots are limited to 128.` };
        } catch (error) {
            if (!this.dead) this.status.textContent = error.message;
            return { errors: [error.message], message: error.message };
        }
    }
    select(id, browse = false) {
        this.controller.edit(state => { state.editor.activeId = id; }, false);
        if (browse) { void this.loadList(this.source); this.browser.open(); }
    }
    createRow(id) {
        const rowFor = () => this.config.images.find(row => row.id === id);
        const card = element('article', 'eit-slot'), top = element('div', 'eit-top');
        const drag = button('⠿', 'Drag image', () => this.select(id)); drag.draggable = true; drag.className = 'eit-drag';
        drag.ondragstart = event => { event.dataTransfer.setData('text/eclipse-image-timeline', id); event.stopPropagation(); };
        drag.ondragend = () => { for (const view of this.views.values()) view.card.classList.remove('eit-drop'); };
        card.ondragover = event => { if (event.dataTransfer.types.includes('text/eclipse-image-timeline')) { event.preventDefault(); card.classList.add('eit-drop'); } };
        card.ondragleave = () => card.classList.remove('eit-drop');
        card.ondrop = event => {
            const from = event.dataTransfer.getData('text/eclipse-image-timeline');
            if (from) { event.preventDefault(); event.stopPropagation(); card.classList.remove('eit-drop'); this.edit(state => state.move(from, id)); }
        };
        const include = button('', 'Include image', () => this.update(id, { enabled: !rowFor().enabled }));
        const choose = button('', 'Choose image', () => this.select(id, true)); choose.className = 'eit-file';
        const up = button('↑', 'Move image up', () => this.edit(state => state.move(id, -1)));
        const down = button('↓', 'Move image down', () => this.edit(state => state.move(id, 1)));
        const remove = button('×', 'Remove image slot', () => this.edit(state => state.remove(id)));
        const toggle = button('', 'Image settings', () => {
            this.controller.edit(state => { const open = state.editor.open ??= {}; open[id] = !open[id]; state.editor.activeId = id; }, false);
        });
        top.append(drag, include, choose, up, down, toggle, remove);
        const summary = button('', 'Preview image', () => this.select(id)); summary.className = 'eit-summary';
        const body = element('div', 'eit-fields'), grid = element('div', 'en-panel-grid'), inputs = {};
        for (const [key, label, options] of [
            ['fit', 'Fit', ['pad', 'crop', 'stretch', 'inherit']],
            ['crop_x', 'Horizontal crop', ['left', 'center', 'right']],
            ['crop_y', 'Vertical crop', ['top', 'center', 'bottom']],
            ['blend_mode', 'Blend to next', this.controller.spec.blend_modes],
        ]) {
            const field = element('label', 'en-panel-field'), input = element('select'); inputs[key] = input;
            field.append(element('span', '', label)); input.setAttribute('aria-label', label);
            for (const value of options) {
                const option = element('option', '', title(value)); option.value = value;
                if (key === 'blend_mode') option.title = this.controller.spec.blend_tooltips?.[value] ?? '';
                input.append(option);
            }
            input.onchange = () => this.update(id, { [key]: input.value }); field.append(input); grid.append(field);
        }
        const label = element('label', 'en-panel-field'), duration = inputs.blend_duration = element('input');
        label.append(element('span', '', 'Blend seconds')); duration.type = 'number'; duration.min = '0'; duration.max = '60'; duration.step = '0.1';
        duration.setAttribute('aria-label', 'Blend seconds'); duration.title = 'Centered on the planned transition. Short image intervals limit its duration. The last image has no outgoing blend.';
        duration.oninput = () => { if (duration.value !== '' && duration.checkValidity()) this.update(id, { blend_duration: duration.valueAsNumber }); };
        duration.onchange = () => { duration.value = rowFor().blend_duration; }; label.append(duration); grid.append(label);
        const metadata = button('Use metadata', 'Use metadata from this image', () => { this.update(id, { use_metadata: !rowFor().use_metadata }); this.select(id); });
        metadata.title = 'Use this image as the single downstream source. Select its sampler, prompts and seed in Image metadata.';
        const actions = element('div', 'eit-slot-actions'); actions.append(metadata);
        body.append(grid, actions); card.append(top, summary, body);
        return { card, include, choose, up, down, toggle, summary, body, inputs, metadata };
    }
    render() { this.controller.root.replaceChildren(this.content); this.syncSummaries(); }
    syncSummaries() {
        if (this.dead) return;
        const rows = this.config.images, ids = new Set(rows.map(row => row.id));
        for (const [id, view] of this.views) if (!ids.has(id)) { view.card.remove(); this.views.delete(id); }
        for (const [index, row] of rows.entries()) {
            let view = this.views.get(row.id); if (!view) { view = this.createRow(row.id); this.views.set(row.id, view); }
            if (this.list.children[index] !== view.card) this.list.insertBefore(view.card, this.list.children[index] ?? null);
            view.card.setAttribute('aria-label', `Image slot ${index + 1}`); view.card.setAttribute('aria-current', String(row.id === this.state.editor.activeId));
            view.card.classList.toggle('eit-disabled', !row.enabled);
            view.include.textContent = row.enabled ? '✓' : '×'; view.include.setAttribute('aria-pressed', String(row.enabled));
            view.choose.textContent = row.file?.filename ?? 'Choose image…'; view.choose.title = fileKey(row.file) || 'Choose image';
            view.up.disabled = !index; view.down.disabled = index === rows.length - 1;
            const open = this.state.editor.open?.[row.id] ?? false;
            view.toggle.textContent = open ? '▾' : '▸'; view.toggle.setAttribute('aria-expanded', String(open)); view.body.hidden = !open;
            view.summary.textContent = `${title(row.fit)} · ${title(row.blend_mode)}${row.use_metadata ? ' · Metadata' : ''}`;
            for (const [key, input] of Object.entries(view.inputs)) if (document.activeElement !== input) input.value = row[key];
            view.inputs.crop_x.disabled = view.inputs.crop_y.disabled = !['crop', 'inherit'].includes(row.fit);
            view.inputs.blend_duration.disabled = ['inherit', 'cut'].includes(row.blend_mode);
            view.inputs.blend_mode.title = this.controller.spec.blend_tooltips?.[row.blend_mode] ?? 'Transition into the next enabled image. The last image has no outgoing transition.';
            view.metadata.disabled = !row.enabled || !row.file; view.metadata.setAttribute('aria-pressed', String(row.use_metadata));
        }
        for (const [key, input] of Object.entries(this.canvasInputs)) if (document.activeElement !== input) input.value = this.config[key];
        this.count.textContent = `${rows.filter(row => row.file && row.enabled).length} included · ${rows.length}/128 slots`; this.add.disabled = rows.length >= 128;
        const file = this.state.active()?.file, key = fileKey(file);
        if (this.previewKey !== key) {
            this.previewKey = key; this.status.textContent = '';
            this.source = file?.source ?? 'input'; this.browser.setSource(this.source);
            this.browser.setFiles(this.lists[this.source] ?? [], file?.filename ?? '');
            if (file) this.image.src = imageURL(file.filename, file.source) + `&cb=${Date.now()}`;
            else this.image.removeAttribute('src');
        }
        this.picture.hidden = !file; this.empty.hidden = !!file;
        this.previewSize(); this.syncMetadata(); this.controller.measure();
    }
    previewSize() {
        if (this.dead) return;
        const first = this.config.images.find(row => row.enabled && row.file)?.file, key = fileKey(first);
        if (key && !this.sizes.has(key) && this.sizeKey !== key) {
            this.sizeKey = key;
            if (this.sizeProbe) this.sizeProbe.onload = this.sizeProbe.onerror = null;
            const probe = this.sizeProbe = new Image();
            probe.onload = () => { if (!this.dead) { this.sizes.set(key, [probe.naturalWidth, probe.naturalHeight]); this.previewSize(); } };
            probe.src = imageURL(first.filename, first.source);
        }
        const [sourceW, sourceH] = this.sizes.get(key) ?? [1, 1];
        const dimensions = {}, sources = [];
        for (const key of ['width', 'height']) {
            const link = this.dimensionLink(key), saved = this.inputSizes?.[key];
            const known = link !== null && saved?.link === link;
            dimensions[key] = known && saved.value !== null ? saved.value : this.config[key];
            sources.push(`${title(key)}: ${link === null ? 'local' : !known ? 'input pending' : saved.value === null ? 'local (empty input)' : 'input'}`);
        }
        let { width, height } = dimensions;
        if (!width && !height) [width, height] = [sourceW, sourceH];
        else if (!width) width = Math.max(1, Math.round(height * sourceW / sourceH));
        else if (!height) height = Math.max(1, Math.round(width * sourceH / sourceW));
        const scale = Math.min(this.frame.clientWidth / width, this.frame.clientHeight / height);
        this.picture.style.width = `${Math.max(0, width * scale)}px`; this.picture.style.height = `${Math.max(0, height * scale)}px`;
        const row = this.state.active();
        this.image.style.objectFit = ({ crop: 'cover', stretch: 'fill' })[row?.fit] ?? 'contain';
        this.image.style.objectPosition = `${({ left: 0, right: 100 })[row?.crop_x] ?? 50}% ${({ top: 0, bottom: 100 })[row?.crop_y] ?? 50}%`;
        this.canvasNote.textContent = `Preview canvas: ${width} × ${height}. ${sources.join(' · ')}. 0 = automatic.${row?.fit === 'inherit' ? ' Inherited fit previews as Pad; the renderer decides the final fit.' : ''}`;
        this.updateActions.querySelector('button').title = this.hasDimensionInputs()
            ? 'Resolve connected width/height once for all image crop previews. Runs this loader and required upstream nodes; downstream rendering stays idle.'
            : 'Refresh all image crop previews using local width/height. No workflow is queued.';
    }
    syncMetadata() {
        const file = this.state.active()?.file, key = this.state.editor.metadataOpen ? fileKey(file) : '';
        if (key !== this.metadataKey) {
            this.metadataKey = key; this.metadataValues = null; this.metadataError = ''; this.metadataAbort?.abort();
            if (key) { this.metadataAbort = new AbortController(); void this.readMetadata(file, key, this.metadataAbort.signal); }
        }
        this.renderMetadata();
    }
    async readMetadata(file, key, signal) {
        try {
            const response = await api.fetchApi('/eclipse-nova/load_image/metadata?' + new URLSearchParams(imageParams(file.filename, file.source)), { cache: 'no-store', signal });
            const data = await response.json(); if (!response.ok) throw Error(data.error ?? 'Unable to read metadata.');
            if (this.dead || signal.aborted || key !== this.metadataKey) return;
            this.metadataValues = data.values ?? {};
        } catch (error) {
            if (this.dead || signal.aborted || key !== this.metadataKey) return;
            this.metadataError = error.message;
        }
        this.renderMetadata();
    }
    renderMetadata() {
        const row = this.state.active(), open = this.state.editor.metadataOpen ?? false;
        const toggle = button(`${open ? '▾' : '▸'} Image metadata${row?.use_metadata ? ' · Used' : ''}`, 'Image metadata', () => this.controller.edit(state => { state.editor.metadataOpen = !open; }, false));
        toggle.setAttribute('aria-expanded', String(open)); toggle.className = 'en-panel-section-toggle';
        this.meta.replaceChildren(toggle);
        if (!open) return;
        const body = element('div', 'eit-metadata-body'); this.meta.append(body);
        if (!row?.file) { body.append(element('div', 'en-panel-note', 'Choose an image to read its generation settings.')); return; }
        const use = button('Use metadata', 'Use selected image metadata', () => this.update(row.id, { use_metadata: !row.use_metadata }));
        use.setAttribute('aria-pressed', String(row.use_metadata)); use.disabled = !row.enabled; body.append(use);
        body.append(element('div', 'en-panel-note', 'One image supplies the selected metadata groups to the output PIPE.'));
        if (!this.metadataValues) { body.append(element('div', 'en-panel-note', this.metadataError || 'Reading generation settings…')); return; }
        const values = this.metadataValues;
        if (!Object.keys(values).length) body.append(element('div', 'en-panel-note', 'No generation settings found.'));
        for (const [key, fields] of Object.entries(GROUPS)) {
            const field = element('div', 'en-panel-field'), label = element('label'), check = element('input'); check.type = 'checkbox';
            const available = fields.some(name => Object.hasOwn(values, name));
            check.checked = available && row.metadata_fields[key]; check.disabled = !available;
            check.setAttribute('aria-label', `Include ${LABELS[key].toLowerCase()}`);
            check.onchange = () => this.update(row.id, { metadata_fields: { ...row.metadata_fields, [key]: check.checked } });
            label.append(check, element('span', '', LABELS[key])); field.append(label);
            const value = fields.filter(name => Object.hasOwn(values, name)).map(name => `${fields.length > 1 ? `${name}: ` : ''}${values[name]}`).join(' · ');
            if (available && ['positive', 'negative'].includes(key)) {
                const text = element('textarea'); text.rows = 2; text.readOnly = true; text.value = value; text.setAttribute('aria-label', LABELS[key]); field.append(text);
            } else field.append(element('div', 'eit-value', available ? value : 'Not available'));
            body.append(field);
        }
    }
    executed(output) {
        const result = output?.eclipse_image_timeline?.[0]; if (!result) return;
        this.inputSizes = Object.fromEntries(['width', 'height'].map(key => [key, {
            link: this.dimensionLink(key), value: result.input_dimensions?.[key] ?? null,
        }]));
        this.status.textContent = result.report; this.previewSize();
    }
    dispose() { this.epoch = (this.epoch ?? 0) + 1; this.request++; this.browser.close(); this.metadataAbort?.abort(); this.metadataKey = null; this.inputSizes = null; }
    destroy() {
        this.dead = true; this.dispose(); this.events.abort(); this.resize.disconnect(); this.unsubscribe(); this.releaseScroll(); this.browser.destroy();
        this.image.onload = this.image.onerror = null; this.image.removeAttribute('src');
        if (this.sizeProbe) { this.sizeProbe.onload = this.sizeProbe.onerror = null; this.sizeProbe.src = ''; }
    }
}
