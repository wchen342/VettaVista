import {enforceMethodRestriction, logDebug} from "./debug";
import {CACHE_EXPIRY_MS, CachedFilterResult, FilterResult, ServerData} from "./constants";


type UpdateCallback = (data: ServerData) => void;

export class CacheService {
    readonly #cache: Map<string, CachedFilterResult> = new Map();
    readonly #config = {
        cacheExpiry: CACHE_EXPIRY_MS
    } as const;
    #onUpdateCallback: UpdateCallback | null = null;

    constructor() {
        enforceMethodRestriction(
            'CacheService',
            ['job-state-manager.js', 'blacklist-manager.js'],
            ['content-script.js']);
    }

    setUpdateCallback(callback: UpdateCallback): void {
        this.#onUpdateCallback = callback;
    }

    // Job filter cache methods
    getFilterResult(jobId: string | undefined): FilterResult | null {
        if (jobId === undefined) return null;

        const entry = this.#cache.get(jobId);
        if (!entry) {
            logDebug('Cache miss for job:', { jobId });
            return null;
        }

        const entryTime = new Date(entry.timestamp).getTime();
        if (Date.now() - entryTime > this.#config.cacheExpiry) {
            logDebug('Cache entry expired for job:', { jobId });
            this.#cache.delete(jobId);
            return null;
        }

        logDebug('Cache hit for job:', { jobId });
        return entry.result;
    }

    setFilterResult(jobId: string, result: FilterResult): void {
        logDebug('Setting filter result for job:', { jobId, result });
        this.#cache.set(jobId, {
            result,
            timestamp: new Date().toISOString()
        });
        if (this.#onUpdateCallback) {
            this.#onUpdateCallback({
                filterResults: { [jobId]: result }
            });
        }
    }
} 