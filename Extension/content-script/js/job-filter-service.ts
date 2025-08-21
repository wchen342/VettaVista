import {enforceMethodRestriction} from "./debug";
import {
    validateDetailedFilterResponse,
    zip,
    PreliminaryFilterResult,
    DetailedFilterResult, FilterResult, JobInfo
} from "./constants";

type FilterCallback = (jobId: string, result: FilterResult) => void;
type ErrorCallback = (jobId: string, error: Error) => void;

class JobFilterService {
    #filterCallbacks: Set<FilterCallback>;
    #errorCallbacks: Set<ErrorCallback>;
    
    constructor() {
        enforceMethodRestriction(
            'JobFilterService',
            ['job-state-manager.js'],
            ['content-script.js']);
        this.#filterCallbacks = new Set();
        this.#errorCallbacks = new Set();
    }

    // Event subscription methods
    onFilterComplete(callback: FilterCallback): () => void {
        this.#filterCallbacks.add(callback);
        return () => this.#filterCallbacks.delete(callback);
    }

    onFilterError(callback: ErrorCallback): () => void {
        this.#errorCallbacks.add(callback);
        return () => this.#errorCallbacks.delete(callback);
    }

    #notifyFilterComplete(jobId: string, result: FilterResult): void {
        this.#filterCallbacks.forEach(callback => {
            try {
                callback(jobId, result);
            } catch (error) {
                console.error('Error in filter complete callback:', error);
            }
        });
    }

    #notifyFilterError(jobId: string, error: Error): void {
        this.#errorCallbacks.forEach(callback => {
            try {
                callback(jobId, error);
            } catch (err) {
                console.error('Error in filter error callback:', err);
            }
        });
    }
    
    async handleBatchPreliminaryFilter(jobIds: string[], jobInfoMap: Map<string, JobInfo>): Promise<PreliminaryFilterResult[]> {
        if (jobIds.length === 0) return [];

        try {
            // Send message to background script instead of direct fetch
            const response = await new Promise<PreliminaryFilterResult[]>((resolve, reject) => {
                chrome.runtime.sendMessage({
                    type: 'preliminary_filter',
                    data: Array.from(jobInfoMap.values())
                }, response => {
                    if (chrome.runtime.lastError) {
                        reject(chrome.runtime.lastError);
                        return;
                    }
                    if (response.error) {
                        reject(new Error(response.error));
                        return;
                    }
                    resolve(response.data);
                });
            });

            zip(jobIds, response).forEach(([jobId, result]) => {
                this.#notifyFilterComplete(jobId, result);
            });

            return response;
        } catch (error) {
            console.error('Error in preliminary filtering:', error);
            jobIds.forEach((jobId) => {
                this.#notifyFilterError(jobId, error instanceof Error ? error : new Error(String(error)));
            });
            throw error;
        }
    }

    async handleDetailedFilter(jobId: string, jobInfo: JobInfo): Promise<DetailedFilterResult> {
        try {
            // Send message to background script instead of direct fetch
            const response = await new Promise<DetailedFilterResult>((resolve, reject) => {
                chrome.runtime.sendMessage({
                    type: 'detailed_filter',
                    data: jobInfo
                }, response => {
                    if (chrome.runtime.lastError) {
                        reject(chrome.runtime.lastError);
                        return;
                    }
                    if (response.error) {
                        reject(new Error(response.error));
                        return;
                    }
                    resolve(response.data);
                });
            });
            
            if (!validateDetailedFilterResponse(response)) {
                throw new Error('Invalid detailed filter response format');
            }

            this.#notifyFilterComplete(jobId, response);

            return response;
        } catch (error) {
            console.error('Error in detailed filtering:', error);
            this.#notifyFilterError(jobId, error instanceof Error ? error : new Error(String(error)));
            throw error;
        }
    }
}

export { JobFilterService };