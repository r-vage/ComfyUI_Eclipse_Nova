/** Share library reads only while nodes in the same workflow are loading. */
async function receive(promise, signal) {
    signal.throwIfAborted();
    let abort;
    try {
        const data = await new Promise((resolve, reject) => {
            abort = () => reject(signal.reason);
            signal.addEventListener('abort', abort, { once: true });
            promise.then(resolve, reject);
        });
        signal.throwIfAborted();
        return structuredClone(data);
    } finally { signal.removeEventListener('abort', abort); }
}

export class PromptLibrary {
    constructor(fetchApi) { this.fetchApi = fetchApi; this.loads = new WeakMap(); }
    async request(path, options = {}) {
        const response = await this.fetchApi(`/eclipse-nova/smart_prompt${path}`, {
            cache: 'no-store', ...options,
            headers: options.body ? { 'Content-Type': 'application/json' } : {},
        });
        let result;
        try { result = await response.json(); } catch { throw Error(`Prompt library request failed (${response.status}).`); }
        if (!response.ok) throw Error(result.error ?? `Prompt library request failed (${response.status}).`);
        return result;
    }
    beginLoad(graph, signal) {
        signal.throwIfAborted();
        let batch = this.loads.get(graph);
        if (!batch) {
            batch = { requests: new Map(), events: new AbortController(), readers: new Set() };
            this.loads.set(graph, batch);
        }
        const reader = new AbortController();
        const close = () => {
            if (reader.signal.aborted) return;
            reader.abort(); signal.removeEventListener('abort', close); batch.readers.delete(reader);
            if (!batch.readers.size) {
                this.loads.delete(graph); batch.events.abort(); batch.requests.clear();
            }
        };
        batch.readers.add(reader); signal.addEventListener('abort', close, { once: true });
        return {
            read: path => {
                reader.signal.throwIfAborted();
                if (!batch.requests.has(path)) batch.requests.set(path, this.request(path, { signal: batch.events.signal }));
                return receive(batch.requests.get(path), reader.signal);
            },
            close,
        };
    }
}
