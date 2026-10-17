/** Cancellable live previews; no polling and no requests during workflow restore. */
export class WildcardPreview {
    constructor(fetch, receive, fail, timers = globalThis) {
        this.fetch = fetch; this.receive = receive; this.fail = fail; this.timers = timers; this.generation = 0;
    }
    cancel() {
        this.generation++;
        if (this.timer != null) this.timers.clearTimeout(this.timer);
        this.timer = null; this.request?.abort(); this.request = null;
    }
    schedule(configuration, immediate = false) {
        this.cancel(); const generation = this.generation;
        const run = async () => {
            this.timer = null;
            const request = new AbortController(); this.request = request;
            try {
                const response = await this.fetch('/eclipse-nova/wildcards/preview', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ configuration }), signal: request.signal,
                });
                const result = await response.json();
                if (!response.ok || !result.success || typeof result.text !== 'string') throw Error(result.error || 'Could not preview wildcards.');
                if (generation === this.generation && !request.signal.aborted) this.receive(result);
            } catch (error) {
                if (generation === this.generation && !request.signal.aborted) this.fail(error.message);
            } finally { if (this.request === request) this.request = null; }
        };
        if (immediate) return run();
        this.timer = this.timers.setTimeout(run, 180);
    }
}
