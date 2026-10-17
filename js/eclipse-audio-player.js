/** Shared native-rate audio audition, linked trim resolution and route tracking. */
import { api } from './comfy/index.js';
import { numericInputValue } from './eclipse-linked-numbers.js';
export { numericInputValue };
import { markEclipseContextMenuOwner } from './eclipse-context-menu-ownership.js';
import { isConfiguringGraph } from './eclipse-widget-utils.js';
import { findSetterByName, getLink, isSetterPathToRootActive } from './eclipse-set-get-utils.js';

const VIDEO_CONTAINER_EXTENSIONS = new Set([
    '3g2', '3gp', 'avi', 'flv', 'm2ts', 'm4v', 'mkv', 'mov', 'mp4',
    'mpeg', 'mpg', 'mts', 'ogv', 'ts', 'webm', 'wmv',
]);

// Direct mode assignments have no dependable per-node change event in both
// renderers. One lightweight observer serves only the mounted audio nodes.
const sourceWatchers = new Set();
let sourceWatcherTimer = null;
function watchSource(callback) {
    sourceWatchers.add(callback);
    sourceWatcherTimer ??= setInterval(() => {
        if (!isConfiguringGraph()) for (const refresh of sourceWatchers) refresh();
    }, 200);
    return () => {
        sourceWatchers.delete(callback);
        if (!sourceWatchers.size) {
            clearInterval(sourceWatcherTimer);
            sourceWatcherTimer = null;
        }
    };
}

export function audioInputRoute(node) {
    let graph = node.graph;
    const input = node.inputs?.find(i => i.name === 'audio_in');
    const path = [input?.link ?? 'disconnected'];
    const result = available => ({ available, key: JSON.stringify(path) });
    if (input?.link == null) return result(false);
    if (!graph) return result(null);
    let link = getLink(graph, input.link);
    const visited = new Set();
    for (let depth = 0; depth < 64 && link; depth++) {
        const source = graph.getNodeById?.(link.origin_id);
        if (!source) return result(null); // May be an unresolved subgraph boundary.
        const slot = link.origin_slot;
        const key = `${graph.id ?? 'root'}:${source.id}:${slot}:${source.mode}`;
        path.push(key);
        if (visited.has(key)) return result(null);
        visited.add(key);
        if (source.mode === 2) return result(false);
        if (source.mode === 4) {
            // Mirror ComfyUI's public type matching: opposite slot, exact AUDIO,
            // then a compatible input. A bypass without such an input is empty.
            const inputs = source.inputs || [];
            const outputType = source.outputs?.[slot]?.type;
            const matches = input => input && LiteGraph.isValidConnection(input.type, outputType)
                && LiteGraph.isValidConnection(input.type, 'AUDIO');
            const match = matches(inputs[slot]) ? inputs[slot]
                : inputs.find(i => i.type === 'AUDIO') || inputs.find(matches);
            link = getLink(graph, match?.link);
        } else if (source.type === 'GetNode [Eclipse Nova]') {
            // Pure lookup avoids virtual getters' UI alerts during observation.
            const setter = findSetterByName(graph, source.widgets?.[0]?.value);
            if (!setter || (setter.graph !== graph && !isSetterPathToRootActive(setter.graph))) return result(false);
            graph = setter.graph;
            path.push(`setter:${graph.id ?? 'root'}:${setter.node.id}`);
            link = getLink(graph, setter.node.inputs?.[slot]?.link);
        } else if (source.isVirtualNode && source.type === 'Reroute') {
            link = getLink(graph, source.inputs?.[0]?.link);
        } else {
            // Arbitrary routers may return None at execution. Until then keep
            // the input pending; Selected file is an immediate manual override.
            return result(true);
        }
    }
    return result(link ? null : false);
}

function formatPlaybackTime(currentTime, duration) {
    const current = Number.isFinite(currentTime) && currentTime >= 0
        ? currentTime.toFixed(3)
        : '0.000';
    const total = Number.isFinite(duration) && duration >= 0
        ? duration.toFixed(3)
        : '--.---';
    return `${current} / ${total} sec`;
}

function buildViewURL(filename) {
    if (!filename) return '';
    // Files live under input/. Subfolder optional via "sub/file.mp3".
    const parts = String(filename).split('/');
    const name = parts.pop();
    const subfolder = parts.join('/');
    const params = new URLSearchParams({ filename: name, type: 'input', subfolder });
    return api.apiURL(`/view?${params.toString()}`);
}

function isVideoContainer(filename) {
    const cleanName = String(filename || '').split(/[?#]/, 1)[0];
    const leafName = cleanName.split(/[\\/]/).pop() || '';
    const extensionIndex = leafName.lastIndexOf('.');
    if (extensionIndex < 0) return false;
    return VIDEO_CONTAINER_EXTENSIONS.has(leafName.slice(extensionIndex + 1).toLowerCase());
}

export async function uploadFile(file) {
    const fd = new FormData();
    fd.append('image', file, file.name);
    fd.append('type', 'input');
    fd.append('overwrite', 'true');
    const resp = await api.fetchApi('/upload/image', { method: 'POST', body: fd });
    if (resp.status !== 200) throw new Error(`Upload failed: ${resp.status} ${resp.statusText}`);
    const data = await resp.json();
    return data.subfolder ? `${data.subfolder}/${data.name}` : data.name;
}

export function createAudioPlayer(node, settings, { onChange } = {}) {
    node.properties ??= {};
    const selectedSource = () => settings().source || 'Auto';
    const sourceLink = () => node.inputs?.find((input) => input.name === 'audio_in')?.link ?? null;
    const sourceState = route => {
        const state = node.properties.eclipseAudioSource;
        return state?.link === sourceLink() && (state.route == null || state.route === route.key) ? state : null;
    };
    const incomingPreview = (route = audioInputRoute(node)) => {
        const state = sourceState(route);
        return selectedSource() !== 'Selected file' && route.available !== false
            && state?.kind === 'incoming' ? state.preview : null;
    };

    // <audio> DOM widget with a precise clip-relative time readout.
    const preview = document.createElement('div');
    markEclipseContextMenuOwner(preview);
    preview.style.display = 'flex';
    preview.style.flexDirection = 'column';
    preview.style.width = '100%';
    preview.style.gap = '2px';
    preview.addEventListener('contextmenu', (event) => event.stopPropagation());

    const el = document.createElement('audio');
    markEclipseContextMenuOwner(el);
    el.controls = true;
    el.preload = 'metadata';
    el.classList.add('comfy-audio');
    el.style.width = '100%';
    el.addEventListener('contextmenu', (event) => event.stopPropagation());

    const seekSlider = document.createElement('input');
    seekSlider.type = 'range';
    seekSlider.min = '0';
    seekSlider.max = '0';
    seekSlider.step = '0.001';
    seekSlider.value = '0';
    seekSlider.disabled = true;
    seekSlider.setAttribute('aria-label', 'Precise clip playback position');
    seekSlider.title = 'Precise clip playback position';
    seekSlider.style.alignSelf = 'center';
    seekSlider.style.width = 'calc(100% - 8px)';
    seekSlider.style.height = '22px';
    seekSlider.style.margin = '0';
    seekSlider.style.cursor = 'pointer';
    seekSlider.style.accentColor = 'var(--en-accent, var(--p-primary-color, #9b7cff))';

    const timeReadout = document.createElement('output');
    timeReadout.setAttribute('aria-label', 'Clip playback position and duration');
    timeReadout.style.alignSelf = 'flex-end';
    timeReadout.style.color = 'var(--fg-color, #ccc)';
    timeReadout.style.font = '12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
    timeReadout.style.fontVariantNumeric = 'tabular-nums';
    timeReadout.style.lineHeight = '16px';
    timeReadout.style.padding = '0 4px';
    timeReadout.textContent = formatPlaybackTime(0, NaN);

    preview.appendChild(el);
    preview.appendChild(seekSlider);
    preview.appendChild(timeReadout);
    const sourceReadout = document.createElement('div');
    sourceReadout.setAttribute('aria-label', 'Audio preview source');
    sourceReadout.style.font = '12px sans-serif';
    sourceReadout.style.color = 'var(--fg-color, #ccc)';
    sourceReadout.style.padding = '0 4px';
    preview.appendChild(sourceReadout);
    const refreshPlaybackUI = () => {
        const durationAvailable = Number.isFinite(el.duration) && el.duration > 0;
        const current = Number.isFinite(el.currentTime) && el.currentTime >= 0
            ? el.currentTime
            : 0;
        seekSlider.disabled = !durationAvailable;
        seekSlider.max = durationAvailable ? String(el.duration) : '0';
        seekSlider.value = String(durationAvailable ? Math.min(current, el.duration) : 0);
        timeReadout.textContent = formatPlaybackTime(el.currentTime, el.duration);
    };
    const resetPlaybackUI = () => {
        seekSlider.disabled = true;
        seekSlider.max = '0';
        seekSlider.value = '0';
        timeReadout.textContent = formatPlaybackTime(0, NaN);
    };
    const handleSeekInput = () => {
        const seconds = Number(seekSlider.value);
        if (seekSlider.disabled || !Number.isFinite(seconds)) return;
        try { el.currentTime = seconds; } catch (_) {}
        refreshPlaybackUI();
    };
    const handleEnded = () => {
        try { el.currentTime = 0; } catch (_) {}
        refreshPlaybackUI();
    };
    const readoutEvents = [
        'loadedmetadata', 'durationchange', 'timeupdate', 'seeking',
        'seeked', 'play', 'pause'
    ];
    readoutEvents.forEach((eventName) => {
        el.addEventListener(eventName, refreshPlaybackUI);
    });
    seekSlider.addEventListener('input', handleSeekInput);
    seekSlider.addEventListener('change', handleSeekInput);
    el.addEventListener('emptied', resetPlaybackUI);
    el.addEventListener('ended', handleEnded);

    const effectiveTrim = () => {
        const start = trimValue('start_time');
        const duration = trimValue('duration');
        const executed = node.properties.eclipseAudioTrim;
        return {
            start: start ?? executed?.start_time,
            duration: duration ?? executed?.duration,
            pending: start == null || duration == null,
        };
    };
    const buildDecodedURL = (route = audioInputRoute(node), trim = effectiveTrim()) => {
        const incoming = incomingPreview(route);
        const v = incoming
            ? `${incoming.subfolder ? `${incoming.subfolder}/` : ''}${incoming.filename} [temp]`
            : settings().audio;
        if (!v || v === 'none') return '';
        if (trim.start == null || trim.duration == null) return '';
        const params = new URLSearchParams({
            filename: v,
            start_time: trim.start,
            duration: trim.duration
        });
        return api.apiURL(`/eclipse-nova/audio_slice?${params.toString()}`);
    };
    const buildPreviewSource = (route, trim) => {
        const choice = selectedSource();
        const state = sourceState(route);
        const wantsInput = choice === 'Incoming audio' || (choice === 'Auto'
            && route.available !== false && !(state?.kind === 'file' && state.selection !== 'Selected file'));
        if (wantsInput) {
            if (incomingPreview(route)) return { kind: 'incoming', url: buildDecodedURL(route, trim) };
            return { kind: route.available === false ? 'unavailable' : 'pending', url: '' };
        }
        const v = settings().audio;
        if (!v || v === 'none') return { kind: 'none', url: '' };
        if (trim.pending || trim.start > 0 || trim.duration > 0 || isVideoContainer(v)) {
            return { kind: 'decoded', url: buildDecodedURL(route, trim) };
        }
        return { kind: 'raw', url: buildViewURL(v) };
    };

    let pendingStartPlay = null;
    let decodedFallbackAttempted = false;
    let activeSourceKind = 'none';
    let observedState = null;
    let assignedSource = '';
    let resumePlayback = false;
    let disposed = false;
    let stopWatching;
    const clearPendingStartPlay = () => {
        if (!pendingStartPlay) return;
        el.removeEventListener('loadedmetadata', pendingStartPlay);
        pendingStartPlay = null;
    };

    const applySrc = (preservePlayback = false) => {
        if (disposed) return;
        const route = audioInputRoute(node);
        const trim = effectiveTrim();
        const source = buildPreviewSource(route, trim);
        const state = JSON.stringify([route.key, selectedSource(), source, trim]);
        if (state === observedState) return;
        observedState = state;
        onChange?.();
        activeSourceKind = source.kind;
        sourceReadout.textContent = source.kind === 'incoming'
            ? 'Incoming audio (first batch item)'
            : source.kind === 'pending' ? 'Incoming audio: queue to preview'
                : source.kind === 'unavailable' ? 'Incoming audio unavailable: enable/connect its source or select a file'
                    : selectedSource() === 'Selected file' ? 'Selected file (manual)'
                        : 'Selected file (fallback)';
        if (trim.pending) sourceReadout.textContent += source.url
            ? ` — Trim requires execution; computed values are from the last run (${trim.start}s / ${trim.duration}s)`
            : ' — Trim requires execution to preview';
        if (source.url === assignedSource) return;
        resumePlayback = preservePlayback && (!el.paused || (pendingStartPlay && resumePlayback));
        clearPendingStartPlay();
        decodedFallbackAttempted = false;
        assignedSource = source.url;
        resetPlaybackUI();
        try { el.currentTime = 0; } catch (_) {}
        if (source.url) {
            const expected = source.url;
            const startPlay = () => {
                if (disposed || assignedSource !== expected || pendingStartPlay !== startPlay) return;
                if (resumePlayback) el.play().catch(() => {});
                clearPendingStartPlay();
                refreshPlaybackUI();
            };
            if (resumePlayback) {
                pendingStartPlay = startPlay;
                el.addEventListener('loadedmetadata', startPlay);
            }
            el.src = source.url;
        } else el.removeAttribute('src');
        el.load();
    };

    // Browser support varies by codec/container. Retry a failed raw
    // preview once through Eclipse's PyAV decoder, which serves WAV.
    const handlePlaybackError = () => {
        if (activeSourceKind === 'incoming') {
            sourceReadout.textContent = 'Incoming preview unavailable: queue again (check excerpt range)';
            resetPlaybackUI();
            return;
        }
        if (activeSourceKind !== 'raw' || decodedFallbackAttempted) return;
        const fallbackURL = buildDecodedURL();
        if (!fallbackURL) return;
        decodedFallbackAttempted = true;
        activeSourceKind = 'decoded';
        clearPendingStartPlay();
        resetPlaybackUI();
        assignedSource = fallbackURL;
        el.src = fallbackURL;
        el.load();
    };
    el.addEventListener('error', handlePlaybackError);


    function trimValue(name) {
        return node.inputs?.find(input => input.name === name || input.widget?.name === name)?.link != null
            ? numericInputValue(node, name) : settings()[name];
    }
    function executed(message) {
        const kind = message?.audio_source?.[0];
        if (!kind) return;
        const trim = message.audio_trim?.[0];
        if (trim && [trim.start_time, trim.duration].every(value => typeof value === 'number' && Number.isFinite(value) && value >= 0)) {
            node.properties.eclipseAudioTrim = trim;
        }
        node.properties.eclipseAudioSource = {
            kind, link: sourceLink(), preview: message.audio_preview?.[0],
            route: audioInputRoute(node).key, selection: selectedSource(),
        };
        applySrc();
    }
    function restore() {
        const state = node.properties.eclipseAudioSource;
        if (state && state.link !== sourceLink()) delete node.properties.eclipseAudioSource;
        applySrc();
    }
    function connected(type, index) {
        if (type !== 1 || isConfiguringGraph()) return;
        const name = node.inputs?.[index]?.name;
        if (name === 'audio_in') { delete node.properties.eclipseAudioSource; applySrc(); }
        if (['audio_in', 'start_time', 'duration'].includes(name)) {
            queueMicrotask(() => applySrc(true));
        }
    }
    function resume() {
        if (disposed) {
            disposed = false; observedState = null; assignedSource = '';
            readoutEvents.forEach(name => el.addEventListener(name, refreshPlaybackUI));
            seekSlider.addEventListener('input', handleSeekInput);
            seekSlider.addEventListener('change', handleSeekInput);
            el.addEventListener('emptied', resetPlaybackUI);
            el.addEventListener('ended', handleEnded);
            el.addEventListener('error', handlePlaybackError);
        }
        if (!isConfiguringGraph()) applySrc();
        stopWatching ??= watchSource(() => { if (node.id !== -1) applySrc(true); });
    }
    function dispose() {
        disposed = true; stopWatching?.(); stopWatching = null;
        readoutEvents.forEach(name => el.removeEventListener(name, refreshPlaybackUI));
        seekSlider.removeEventListener('input', handleSeekInput);
        seekSlider.removeEventListener('change', handleSeekInput);
        el.removeEventListener('emptied', resetPlaybackUI);
        el.removeEventListener('ended', handleEnded);
        el.removeEventListener('error', handlePlaybackError);
        clearPendingStartPlay();
        try { el.pause(); el.removeAttribute('src'); el.load(); } catch (_) {}
    }
    return { element: preview, audio: el, refresh: applySrc, executed, restore, connected, resume, dispose };
}
