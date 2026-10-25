/** Source-player trim controls. Copyright (c) 2026 r-vage. Apache-2.0. */
import { button, element } from './eclipse-panel-controls.js';

export function sourcePosition(seconds, duration, fps, count) {
    const [numerator, denominator = 1] = String(fps ?? '').split('/').map(Number);
    const rate = numerator / denominator;
    const time = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
    if (!Number.isFinite(rate) || rate <= 0) return { time, rate: null, frame: null, last: null };
    const last = Number.isInteger(count) && count > 0 ? count - 1
        : Number.isFinite(duration) && duration > 0 ? Math.max(0, Math.ceil(duration * rate - 1e-8) - 1) : null;
    const frame = Math.min(last ?? Infinity, Math.floor(time * rate + 1e-5));
    return { time, rate, frame, last };
}

export function sourceTimeLabel(seconds) {
    const milliseconds = Math.max(0, Math.round(seconds * 1000));
    const pad = (value, length = 2) => String(value).padStart(length, '0');
    const hours = Math.floor(milliseconds / 3600000);
    return `${hours ? `${pad(hours)}:` : ''}${pad(Math.floor(milliseconds / 60000) % 60)}:${pad(Math.floor(milliseconds / 1000) % 60)}.${pad(milliseconds % 1000, 3)}`;
}

export function createSourcePositionControls(video, setStart) {
    let source = null, info = null, destroyed = false;
    const root = element('div', 'evl-position'); root.setAttribute('role', 'group'); root.setAttribute('aria-label', 'Source trim controls');
    const label = element('span', 'evl-position-label'); label.setAttribute('aria-label', 'Source preview position');
    label.title = 'Zero-based source frame estimated from the reported source FPS (≈). Variable-frame-rate files need Preview selected trim for exact review.';
    const controls = element('div', 'evl-position-controls');
    const secondsLabel = element('label', '', 'Seconds'), seconds = element('input');
    seconds.type = 'number'; seconds.min = '0'; seconds.step = 'any';
    seconds.setAttribute('aria-label', 'Seek source seconds'); seconds.title = 'Enter a source time in seconds and press Enter. This only moves the preview; Set start here applies it to this slot.';
    secondsLabel.append(seconds);
    const position = () => sourcePosition(video.currentTime, video.duration, info?.fps, info?.frame_count_estimate);
    const ready = () => Boolean(source && video.readyState >= 2 && !video.error && !video.seeking);
    function seek(time) {
        if (!ready() || !Number.isFinite(time)) return;
        video.pause();
        const max = Number.isFinite(video.duration) ? Math.max(0, video.duration - 1e-6) : Infinity;
        video.currentTime = Math.max(0, Math.min(time + 1e-6, max));
        refresh();
    }
    function step(delta) {
        const value = position();
        if (value.frame !== null) seek(Math.max(0, Math.min(value.last ?? Infinity, value.frame + delta)) / value.rate);
    }
    const previous = button('−1f', 'Previous source frame', () => step(-1));
    const next = button('+1f', 'Next source frame', () => step(1));
    const apply = button('Set start here', 'Set start frame from preview', () => {
        const value = position();
        if (!ready() || value.frame === null || value.frame > 2 ** 31 - 1) return;
        video.pause(); setStart(source.id, value.frame);
    });
    previous.title = next.title = 'Step the source preview by one frame at its reported FPS. Does not change the trim until Set start here is clicked.';
    apply.title = 'Use the preview position as this slot’s zero-based Start frame. Load cap stays unchanged. For variable frame rates, check Preview selected trim.';
    const commit = () => { if (seconds.value !== '' && seconds.checkValidity()) seek(seconds.valueAsNumber); };
    seconds.onchange = commit;
    seconds.onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); commit(); seconds.blur(); } };
    controls.append(secondsLabel, previous, next, apply); root.append(label, controls);
    function refresh() {
        if (destroyed || !source) return;
        const value = position(), available = ready();
        const text = video.error ? 'Source preview unavailable' : video.readyState < 2 ? 'Loading source…'
            : `${value.frame === null ? 'Frame unavailable' : `Frame ≈ ${value.frame}`} · ${sourceTimeLabel(value.time)}${video.seeking ? ' · seeking…' : ''}`;
        if (label.textContent !== text) label.textContent = text;
        seconds.disabled = !available;
        if (document.activeElement !== seconds) seconds.value = value.time.toFixed(3);
        previous.disabled = !available || value.frame === null || value.frame <= 0;
        next.disabled = !available || value.frame === null || (value.last !== null && value.frame >= value.last);
        apply.disabled = !available || value.frame === null || value.frame > 2 ** 31 - 1;
    }
    const events = ['loadedmetadata', 'loadeddata', 'durationchange', 'seeking', 'seeked', 'timeupdate', 'pause', 'ended', 'emptied', 'error'];
    for (const event of events) video.addEventListener(event, refresh);
    return {
        element: root, refresh,
        source(row, data) { source = row?.file ? row : null; info = data; root.hidden = !source; refresh(); },
        destroy() { destroyed = true; source = info = null; for (const event of events) video.removeEventListener(event, refresh); },
    };
}
