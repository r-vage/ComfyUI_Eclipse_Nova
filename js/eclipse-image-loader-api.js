/** Deduplicated file catalogs and explicit source invalidation; no background scans. */
import { api } from './comfy/index.js';
const listings = new Map();
export async function imageFiles(source, refresh = false) {
    if (refresh) listings.delete(source);
    if (!listings.has(source)) {
        const request = api.fetchApi(`/eclipse-nova/load_image/${source === 'output' ? 'list_output' : 'list'}`, { cache: 'no-store' })
            .then(async response => { const data = await response.json(); if (!response.ok || !data.success) throw Error(data.error ?? 'Unable to list images.'); return data.files; });
        listings.set(source, request);
        request.catch(() => { if (listings.get(source) === request) listings.delete(source); });
    }
    return listings.get(source);
}
export function imageParams(filename, type) {
    const parts = filename.split('/'); return { filename: parts.pop(), subfolder: parts.join('/'), type };
}
export const imageURL = (filename, type) => api.apiURL('/view?' + new URLSearchParams(imageParams(filename, type)));
export async function postJSON(path, value) {
    const response = await api.fetchApi(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) });
    const data = await response.json(); if (!response.ok || data.success === false || data.error) throw Error(data.error ?? 'Request failed.'); return data;
}
