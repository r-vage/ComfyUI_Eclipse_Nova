/** Persistent video playlist editor. Copyright (c) 2026 r-vage. MIT License. */
import { api } from './comfy/index.js';
import { isConfiguringGraph, onVueModeChange } from './eclipse-widget-utils.js';
import { markEclipseContextMenuOwner } from './eclipse-context-menu-ownership.js';
import { createVideoBrowser, videoElement as el, videoFileKey, videoPath, videoURL } from './eclipse-video-browser.js';
import { createVideoSlots } from './eclipse-video-slots.js';

const acceptsVideo = file => /\.(mp4|webm|mkv|mov|avi|m4v|mpg|mpeg|ts)$/i.test(file.name);
const uuid = () => globalThis.crypto?.randomUUID?.() || `clip-${Date.now()}-${Math.random().toString(16).slice(2)}`;
export function createVideoEditor(node, binding) {
    let disposed = false, revision = 0, probeRevision = 0, job = null, jobRunning = false, poll = null, selectedSource = null;
    let joined = null, joinedStale = false, report = '', uploadChain = Promise.resolve();
    let sourceRange = null, rangeKey = null, seekPending = false, playbackFrame = null;
    let pickerTarget = null, uploadTarget = null;
    const fileRevisions = new Map();
    const probes = new Map(), controllers = new Set();
    const root = el('div', null, 'en-video-playlist');
    root.setAttribute('aria-label', 'Video playlist editor');
    markEclipseContextMenuOwner(root);
    const fileInput = document.createElement('input'); fileInput.type = 'file'; fileInput.multiple = true;
    fileInput.accept = 'video/*,.mkv,.avi,.m4v,.ts'; fileInput.hidden = true;
    const right = el('section', null, 'evl-right'); right.setAttribute('aria-label', 'Selected clip preview');
    const tabs = el('div', null, 'evl-tabs');
    const sourceTab = el('button', 'Source'), joinedTab = el('button', 'Joined'), dataTab = el('button', 'GenData');
    const sourceLabel = el('div', 'Select or drop a video', 'evl-source');
    const video = document.createElement('video'); video.controls = true; video.playsInline = true; video.preload = 'metadata';
    const metadata = document.createElement('pre'); metadata.hidden = true;
    const status = el('div', 'Add videos to begin. Controls are available before queueing.', 'evl-status');
    status.setAttribute('role', 'status');
    const actions = el('div', null, 'evl-actions');
    const build = el('button', 'Build joined preview'), trimPreview = el('button', 'Preview selected trim'), cancel = el('button', 'Cancel preview'); cancel.hidden = true;
    actions.append(trimPreview, build, cancel);
    tabs.append(el('b', 'View:', 'en-panel-bar-label'), sourceTab, joinedTab, dataTab);
    tabs.classList.add('en-panel-bar');
    right.append(tabs, sourceLabel, video, metadata, actions, status);
    root.append(right, fileInput);

    const presentation = () => node.properties?.eclipseVideo || {};
    function changeGraph(action) {
        node.graph?.beforeChange?.();
        action();
        node.graph?.afterChange?.();
        node.setDirtyCanvas?.(true, true);
    }
    function present(patch) {
        const value = { ...presentation(), ...patch };
        if (JSON.stringify(value) === JSON.stringify(presentation())) return;
        changeGraph(() => { node.properties ||= {}; node.properties.eclipseVideo = value; });
    }
    function rows() {
        try {
            const manifest = JSON.parse(binding.playlist());
            if (manifest.version !== 1 || !Array.isArray(manifest.clips)) throw new Error('Unsupported playlist');
            return manifest.clips;
        } catch (error) { status.textContent = `Invalid playlist: ${error.message}`; return []; }
    }
    const currentRow = () => rows().find(row => row.id === presentation().activeId);
    function persist(next, mediaChanged = true) {
        binding.save(next);
        if (mediaChanged) markStale();
        else status.textContent = 'Metadata source saved.';
        render();
    }
    function editRow(id, patch) {
        const next = rows().map(row => {
            let value = row.id === id ? { ...row, ...patch } : { ...row };
            if (patch.use_metadata && row.id !== id) value.use_metadata = false;
            if (!value.enabled || !value.file) value.use_metadata = false;
            return value;
        });
        if ('start_frame' in patch || 'load_cap' in patch) {
            present({ activeId: id, tab: 'source' });
        }
        persist(next, Object.keys(patch).some(name => name !== 'use_metadata'));
    }
    function addFiles(files) {
        const next = rows();
        let added = null;
        for (const file of files) {
            const empty = next.find(row => !row.file);
            if (next.length >= 128 && !empty) { status.textContent = 'A playlist supports at most 128 clips.'; break; }
            const ref = { type: file.type || 'input', subfolder: file.subfolder || '', filename: file.filename || file.name };
            added = empty || { id: uuid(), start_frame: 0, load_cap: 0, enabled: true, mute: false, use_metadata: false };
            added.file = ref;
            fileRevisions.set(added.id, (fileRevisions.get(added.id) || 0) + 1);
            if (!empty) next.push(added);
        }
        if (added) { present({ activeId: added.id, tab: 'source', openClips: [...new Set([...(presentation().openClips || []), added.id])] }); persist(next); }
        void probeRows();
    }
    function move(delta, id = presentation().activeId) {
        const next = rows(), index = next.findIndex(row => row.id === id);
        if (index < 0 || index + delta < 0 || index + delta >= next.length) return;
        [next[index], next[index + delta]] = [next[index + delta], next[index]];
        persist(next);
    }
    function setTab(tab) { present({ tab }); updatePlayer(); }
    sourceTab.onclick = () => setTab('source'); joinedTab.onclick = () => setTab('joined'); dataTab.onclick = () => setTab('metadata');
    function duplicateRow(id = presentation().activeId) {
        const next = rows(), row = next.find(item => item.id === id); if (!row || next.length >= 128) return;
        const copy = { ...row, id: uuid(), use_metadata: false };
        next.splice(next.findIndex(item => item.id === row.id) + 1, 0, copy);
        present({ activeId: copy.id }); persist(next);
    }
    function removeRow(id = presentation().activeId) {
        const row = rows().find(item => item.id === id); if (!row) return;
        const next = rows().filter(item => item.id !== row.id);
        fileRevisions.set(id, (fileRevisions.get(id) || 0) + 1);
        present({ activeId: id === presentation().activeId ? next[0]?.id || null : presentation().activeId,
            openClips: (presentation().openClips || []).filter(key => key !== id) }); persist(next);
    }
    function assignFile(id, file) {
        const next = rows(), row = next.find(item => item.id === id); if (!row) return;
        fileRevisions.set(id, (fileRevisions.get(id) || 0) + 1);
        row.file = { type: file.type || 'input', subfolder: file.subfolder || '', filename: file.filename || file.name };
        present({ activeId: id, tab: 'source', openClips: [...new Set([...(presentation().openClips || []), id])] });
        persist(next); void probeRows();
    }
    const slotEditor = createVideoSlots({
        effects: binding.effects,
        rows, state: presentation, present, probe: file => probes.get(videoFileKey(file)), update: editRow,
        select(id) { present({ activeId: id, tab: 'source' }); render(); },
        choose(id) { browser.close(); pickerTarget = id; present({ activeId: id, tab: 'source' }); render(); browser.open(); },
        add() {
            const next = rows(); if (next.length >= 128) return;
            const row = { id: uuid(), file: null, start_frame: 0, load_cap: 0, enabled: true, mute: false, use_metadata: false };
            next.push(row); present({ activeId: row.id, tab: 'source' }); persist(next);
        },
        remove: removeRow, duplicate: duplicateRow, move: (id, delta) => move(delta, id),
        reorder(from, to) {
            const next = rows(), a = next.findIndex(row => row.id === from), b = next.findIndex(row => row.id === to);
            if (a >= 0 && b >= 0 && a !== b) { next.splice(b, 0, next.splice(a, 1)[0]); persist(next); }
        },
    });
    root.prepend(slotEditor.element);
    function source(file) {
        const key = file ? videoFileKey(file) : null;
        if (key === selectedSource) return;
        selectedSource = key;
        rangeKey = null; sourceRange = null; seekPending = false;
        video.pause();
        if (file) { video.src = videoURL('/view', file); video.load(); }
        else { video.removeAttribute('src'); video.load(); }
    }
    function stopPlaybackWatch() {
        if (playbackFrame !== null) cancelAnimationFrame(playbackFrame);
        playbackFrame = null;
    }
    function seekRangeStart() {
        if (!sourceRange || video.readyState < 1) return;
        seekPending = false;
        // Seek just inside the frame: media timestamps are quantized to µs,
        // and floating-point subtraction can otherwise show the preceding one.
        video.currentTime = sourceRange.start + 1e-6;
    }
    function applySourceRange(row, info) {
        // HTML video seeks by seconds, not frame index. The exact trim button
        // uses decoded source timestamps when a file has variable frame timing.
        const [numerator, denominator = 1] = String(info?.fps || '').split('/').map(Number);
        const rate = numerator / denominator;
        const key = row && rate > 0 && Number.isFinite(rate) ? `${row.id}:${row.start_frame}:${row.load_cap}:${rate}` : null;
        if (key === rangeKey) return;
        rangeKey = key; sourceRange = null; seekPending = false;
        if (!key) return;
        const duration = Number.isFinite(info.duration) ? info.duration : Infinity;
        const start = Math.min(row.start_frame / rate, Math.max(0, duration - 1 / rate));
        const end = Math.min(row.load_cap ? (row.start_frame + row.load_cap) / rate : duration, duration);
        sourceRange = { start, end, last: Math.max(start, end - 1 / rate), capped: end < duration };
        video.pause(); seekPending = true; seekRangeStart();
    }
    function checkRangeEnd() {
        if (!sourceRange?.capped || video.paused || video.currentTime < sourceRange.end) return;
        video.pause();
        video.currentTime = sourceRange.last + 1e-6;
    }
    function watchPlayback() {
        playbackFrame = null;
        if (disposed || video.paused) return;
        checkRangeEnd();
        if (sourceRange && !video.paused) playbackFrame = requestAnimationFrame(watchPlayback);
    }
    video.addEventListener('loadedmetadata', () => { if (seekPending) seekRangeStart(); });
    video.addEventListener('play', () => {
        if (!sourceRange) return;
        if (video.currentTime < sourceRange.start || video.currentTime >= sourceRange.last) seekRangeStart();
        stopPlaybackWatch(); playbackFrame = requestAnimationFrame(watchPlayback);
    });
    video.addEventListener('pause', stopPlaybackWatch);
    video.addEventListener('timeupdate', checkRangeEnd);
    function updatePlayer() {
        const tab = presentation().tab || 'source', row = currentRow();
        for (const [button, value] of [[sourceTab, 'source'], [joinedTab, 'joined'], [dataTab, 'metadata']]) button.setAttribute('aria-pressed', String(tab === value));
        video.hidden = tab === 'metadata'; metadata.hidden = tab !== 'metadata';
        if (tab === 'metadata') {
            rangeKey = null; sourceRange = null; seekPending = false;
            video.pause();
            const info = row?.file ? probes.get(videoFileKey(row.file)) : null;
            metadata.textContent = info?.parameters ? `${info.parameters.status}\n\n${JSON.stringify(info.parameters.data, null, 2)}` : 'Select a clip to inspect saved prompts and sampling settings.';
            sourceLabel.textContent = row?.file ? `${row.file.filename}${row.use_metadata ? ' • downstream GenData source' : ''}` : 'No selected file';
        } else if (tab === 'joined') {
            source(joined);
            applySourceRange(null, null);
            sourceLabel.textContent = joined ? (joinedStale ? 'Joined preview is stale — rebuild after edits' : 'Joined result') : 'Build a preview or queue the node';
        } else {
            const file = row?.file;
            source(file);
            const info = file ? probes.get(videoFileKey(file)) : null;
            applySourceRange(row, info);
            sourceLabel.textContent = file ? `${file.filename}${info?.width ? ` · ${info.width}×${info.height} · ${info.duration?.toFixed(2) || '?'} s · ${info.fps || '?'} fps` : ''}` : 'Choose a video in the selected slot';
        }
    }
    function render() {
        if (disposed) return;
        const all = rows(), active = currentRow();
        slotEditor.render();
        trimPreview.disabled = !active;
        trimPreview.disabled ||= jobRunning || !active?.file;
        build.disabled = !all.some(row => row.enabled && row.file) || jobRunning;
        updatePlayer(); binding.measure();
    }
    async function probeRows() {
        const requestedRevision = probeRevision;
        for (const row of rows()) {
            if (disposed || requestedRevision !== probeRevision) return;
            if (!row.file) continue;
            const key = videoFileKey(row.file);
            if (probes.has(key)) continue;
            probes.set(key, { loading: true });
            const controller = new AbortController(); controllers.add(controller);
            try {
                const response = await api.fetchApi(videoPath('/eclipse-nova/load_video/probe', row.file), { signal: controller.signal, cache: 'no-store' });
                const info = await response.json();
                if (disposed || controller.signal.aborted || requestedRevision !== probeRevision) return;
                probes.set(key, info); render();
                if (info.error) status.textContent = `${row.file.filename}: ${info.error}`;
            } catch (error) { if (!disposed && requestedRevision === probeRevision && error.name !== 'AbortError') { probes.set(key, { error: error.message }); render(); } }
            finally { controllers.delete(controller); }
        }
    }
    const browser = createVideoBrowser({
        getState: () => presentation().browser || {},
        onStateChange: value => present({ browser: value }),
        onChoose: file => assignFile(pickerTarget, file),
        onUpload() { uploadTarget = pickerTarget; fileInput.multiple = false; fileInput.click(); },
    });
    function uploadFiles(files, target = null) {
        const selected = [...files].filter(acceptsVideo);
        const generation = probeRevision, ticket = (fileRevisions.get(target) || 0) + 1;
        if (target) fileRevisions.set(target, ticket);
        uploadChain = uploadChain.then(async () => {
            const failures = [];
            for (const [index, file] of selected.entries()) {
                if (disposed || generation !== probeRevision) return;
                status.textContent = `Uploading ${index + 1}/${selected.length}: ${file.name}`;
                const controller = new AbortController(); controllers.add(controller);
                try {
                    const data = new FormData(); data.append('image', file, file.name); data.append('type', 'input'); data.append('overwrite', 'false');
                    const response = await api.fetchApi('/upload/image', { method: 'POST', body: data, signal: controller.signal });
                    const saved = await response.json();
                    if (!response.ok) throw new Error(saved.error || 'Upload failed');
                    if (!disposed && generation === probeRevision) {
                        const file = { type: saved.type || 'input', subfolder: saved.subfolder || '', filename: saved.name };
                        if (!target) addFiles([file]);
                        else if (fileRevisions.get(target) === ticket) assignFile(target, file);
                    }
                } catch (error) { if (!disposed && generation === probeRevision && error.name !== 'AbortError') failures.push(`${file.name}: ${error.message}`); }
                finally { controllers.delete(controller); }
            }
            if (!disposed && generation === probeRevision) status.textContent = failures.length ? failures.join('\n') : 'Uploads finished. Start frame and load cap count original frames; 0 cap means all remaining.';
        });
    }
    fileInput.onchange = () => { uploadFiles(fileInput.files, uploadTarget); fileInput.value = ''; uploadTarget = null; browser.close(); };
    root.ondragover = event => { if (event.dataTransfer.files?.length || event.dataTransfer.types.includes('Files')) { event.preventDefault(); root.classList.add('evl-dragover'); } };
    root.ondragleave = () => root.classList.remove('evl-dragover');
    root.ondrop = event => { root.classList.remove('evl-dragover'); if (event.dataTransfer.files.length) { event.preventDefault(); event.stopPropagation(); uploadFiles(event.dataTransfer.files); } };
    async function releaseJob() {
        if (poll) clearTimeout(poll); poll = null;
        const previous = job; job = null; jobRunning = false; cancel.hidden = true;
        if (previous) { try { await api.fetchApi(`/eclipse-nova/load_video/preview/${previous}`, { method: 'DELETE', keepalive: true }); } catch { /* server expiry also cleans abandoned jobs */ } }
    }
    function markStale() {
        revision++; joinedStale = Boolean(joined);
        if (jobRunning) void releaseJob();
        status.textContent = 'Settings saved. Queue to join videos, or build a viewing preview.';
    }
    async function buildPreview(selectedOnly) {
        const row = currentRow(); if (selectedOnly && !row?.file) return;
        await releaseJob();
        const requestedRevision = ++revision;
        let payload;
        try {
            payload = binding.options();
            payload.playlist = selectedOnly ? JSON.stringify({ version: 1, clips: [{ ...row, enabled: true, use_metadata: false }] })
                : JSON.stringify({ version: 1, clips: rows().filter(item => item.file) });
        } catch (error) { status.textContent = error.message; return; }
        status.textContent = 'Building preview…'; jobRunning = true; cancel.hidden = false; render();
        try {
            const response = await api.fetchApi('/eclipse-nova/load_video/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Preview request failed');
            if (disposed || requestedRevision !== revision) { await api.fetchApi(`/eclipse-nova/load_video/preview/${data.id}`, { method: 'DELETE' }); return; }
            job = data.id; jobRunning = true; cancel.hidden = false;
            async function check() {
                if (!job || disposed || requestedRevision !== revision) return;
                try {
                    const response = await api.fetchApi(`/eclipse-nova/load_video/preview/${job}`);
                    const data = await response.json();
                    if (disposed || requestedRevision !== revision) return;
                    if (!response.ok || data.status === 'error') throw new Error(data.error || 'Preview failed');
                    if (data.status === 'complete') {
                        joined = data.result; joinedStale = false; jobRunning = false; cancel.hidden = true;
                        status.textContent = selectedOnly ? 'Selected trim preview ready.' : 'Joined preview ready.';
                        present({ tab: 'joined' }); render();
                    } else poll = setTimeout(check, 500);
                } catch (error) { status.textContent = error.message; await releaseJob(); render(); }
            }
            void check();
        } catch (error) { if (!disposed && requestedRevision === revision) { status.textContent = error.message; await releaseJob(); render(); } }
    }
    build.onclick = () => void buildPreview(false); trimPreview.onclick = () => void buildPreview(true);
    cancel.onclick = () => { revision++; void releaseJob().then(render); status.textContent = 'Preview cancelled.'; };
    video.addEventListener('error', () => { if (!disposed) status.textContent = 'Source cannot play in this browser or preview expired. Build a compatible preview.'; });
    for (const event of ['pointerdown', 'pointerup', 'pointermove', 'keydown', 'keyup', 'wheel', 'contextmenu']) root.addEventListener(event, e => e.stopPropagation());
    const unsubscribe = onVueModeChange(() => browser.close());
    function refreshSettings() {
        if (node.id === -1) return;
        // The flexible preview absorbs control-row changes inside the user's
        // current/saved size. Fitting to content here would shrink every edit.
        node.setDirtyCanvas?.(true, true);
    }
    const originalDragOver = node.onDragOver, originalDrop = node.onDragDrop;
    node.onDragOver = function (event) { return [...(event.dataTransfer?.files || [])].some(acceptsVideo) || originalDragOver?.apply(this, arguments); };
    node.onDragDrop = function (event) { if ([...(event.dataTransfer?.files || [])].some(acceptsVideo)) { uploadFiles(event.dataTransfer.files); return true; } return originalDrop?.apply(this, arguments); };
    const pageHide = () => {
        revision++; void releaseJob(); joined = null; selectedSource = undefined;
        render();
    };
    window.addEventListener('pagehide', pageHide);
    render();
    if (!isConfiguringGraph()) requestAnimationFrame(() => { if (!disposed) { refreshSettings(); void probeRows(); } });
    let cleaned = false;
    function destroy() {
        if (cleaned) return;
        cleaned = disposed = true; revision++;
        for (const controller of controllers) controller.abort();
        controllers.clear(); void releaseJob(); browser.destroy(); slotEditor.destroy(); unsubscribe();
        window.removeEventListener('pagehide', pageHide);
        stopPlaybackWatch();
        video.pause(); video.removeAttribute('src'); video.load();
    }
    return {
        element: root, controls: actions, destroy,
        minimumHeight: () => Math.max(270, tabs.offsetHeight + actions.offsetHeight + status.offsetHeight + 160),
        close: () => browser.close(),
        settingsChanged() { markStale(); refreshSettings(); render(); void probeRows(); },
        restore() {
            revision++; probeRevision++; void releaseJob(); joined = null; selectedSource = undefined;
            for (const controller of controllers) controller.abort();
            probes.clear();
            refreshSettings(); render(); void probeRows();
        },
        executed(message) {
            void releaseJob(); joined = message?.eclipse_video?.[0] || null; joinedStale = false;
            report = message?.eclipse_report?.[0] || '';
            status.textContent = joined ? 'Joined output ready.' : 'Joined preview unavailable.';
            status.title = report.slice(-2000);
            if (joined) present({ tab: 'joined' });
            render();
        },
    };
}

