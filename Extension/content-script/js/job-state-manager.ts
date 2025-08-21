import {logDebug, logError, logInfo} from "./debug";
import {
    BatchConfig,
    FilterResult,
    JobHistoryEntry,
    jobIdType,
    JobInfo,
    JobState,
    JobStateData,
    JobStatus
} from "./constants";
import {JobFilterService} from "./job-filter-service";
import {BlacklistManager} from "./blacklist-manager";
import {JobHistoryManager} from "./job-history-manager";

type StateChangeCallback = (jobId: string, state: JobStateData) => void;

export class JobStateManager {
    // Private fields
    #jobStates: Map<jobIdType, JobStateData> = new Map();
    #stateChangeCallbacks: Set<StateChangeCallback> = new Set();
    #processingBatch: Set<jobIdType> = new Set();
    #pendingBatch: Set<jobIdType> = new Set();
    #batchProcessingTimeout: ReturnType<typeof setTimeout> | null = null;
    #filterService: JobFilterService;
    #blacklistManager: BlacklistManager;
    #jobHistoryManager: JobHistoryManager;

    constructor(
        filterService: JobFilterService,
        blacklistManager: BlacklistManager,
        historyManager: JobHistoryManager
    ) {
        this.#filterService = filterService;
        this.#blacklistManager = blacklistManager;
        this.#jobHistoryManager = historyManager;

        // Subscribe to filter service events
        this.#filterService.onFilterComplete(async (jobId: string, result: FilterResult) => {
            await this.completeProcessing(jobId, result.status, {
                tooltip: result.reasons?.join('\n'),
                filterResult: result
            });
        });

        this.#filterService.onFilterError(async (jobId: string, error: Error) => {
            await this.handleError(jobId, error);
        });

        // Subscribe to blacklist changes
        this.#blacklistManager.subscribe(async (company: string, action: 'add' | 'remove', metadata: { reason?: string }) => {
            logInfo(`Handling blacklist ${action} for company:`, company);
            const jobs = this.getJobsByCompany(company);
            
            for (const jobId of jobs) {
                if (action === 'add') {
                    await this.updateJobState(jobId, JobState.BLACKLISTED, {
                        ...this.getJobState(jobId),
                        company: company,
                        filterResult: { status: JobStatus.CONFIRMED_NO_MATCH },
                        tooltip: `Company ${company} is blacklisted${metadata.reason ? `: ${metadata.reason}` : ''}`
                    });
                } else if (action === 'remove') {
                    // Reset to initial state when company is removed from blacklist
                    const currentState = this.getJobState(jobId);
                    await this.updateJobState(jobId, JobState.INITIAL, {
                        filterResult: {status:JobStatus.UNKNOWN},
                        company: company,  // Maintain the company information
                        tooltip: '',
                        // Preserve other metadata that might be important
                        jobInfo: currentState?.jobInfo
                    });
                }
            }
        });
    }

    // State management
    getJobState(jobId: string): JobStateData | undefined {
        return this.#jobStates.get(jobId);
    }

    async updateJobState(jobId: string, newState: JobState, jobStateData: Partial<JobStateData>): Promise<JobStateData> {
        const currentState = this.getJobState(jobId);

        // Create new state object, preserving existing fields if metadata is empty
        const state: JobStateData = {
            ...currentState,                // Preserve ALL existing fields
            ...jobStateData,                   // Apply any new metadata fields
            state: newState,               // Update state
            timestamp: new Date().toISOString(),  // Update timestamp
            jobInfo: jobStateData.jobInfo || currentState?.jobInfo || {} as JobInfo,  // Ensure JobInfo type
            filterResult: jobStateData.filterResult || currentState?.filterResult || {} as FilterResult  // Ensure FilterResult type
        };

        // Store new state
        this.#jobStates.set(jobId, state);
        
        // Notify subscribers
        this.#notifyStateChange(jobId, state);
        
        return state;
    }

    // Handle blacklist button click
    async handleBlacklistButtonClick(jobId: string, company: string, reason: string = ''): Promise<void> {
        const isBlacklisted = await this.#blacklistManager.isCompanyBlacklisted(company);
        
        if (isBlacklisted) {
            await this.#blacklistManager.removeCompany(company);
        } else {
            await this.#blacklistManager.addCompany(company, reason);
        }
    }

    // Company-related methods
    getJobsByCompany(company: string): string[] {
        const jobs: string[] = [];
        for (const [jobId, state] of this.#jobStates) {
            if (state.jobInfo?.company === company) {
                jobs.push(jobId);
            }
        }
        return jobs;
    }

    // Subscription management
    subscribe(callback: StateChangeCallback): () => void {
        this.#stateChangeCallbacks.add(callback);
        return () => this.#stateChangeCallbacks.delete(callback);
    }

    #notifyStateChange(jobId: string, state: JobStateData): void {
        for (const callback of this.#stateChangeCallbacks) {
            try {
                callback(jobId, state);
            } catch (error) {
                console.error('Error in state change callback:', error);
            }
        }
    }

    // Batch management
    isProcessing(jobId: string): boolean {
        // Enhanced to check both processing and filtering states
        const state = this.getJobState(jobId);
        return this.#processingBatch.has(jobId) || 
               this.#pendingBatch.has(jobId) ||
               state?.state === JobState.FILTERING;
    }

    async addToBatch(jobId: string, jobInfo: JobInfo): Promise<void> {
        logDebug('State manager: Adding job to batch:', { jobId, jobInfo });
        
        // Check if already processing
        if (this.isProcessing(jobId)) {
            logDebug('State manager: Job already processing:', jobId);
            return Promise.reject(new Error('Job is already being processed'));
        }

        // Add to pending batch
        logDebug('State manager: Adding to pending batch:', jobId);
        this.#pendingBatch.add(jobId);
        await this.updateJobState(jobId, JobState.FILTERING, {
            jobInfo,
            filterResult: {status:JobStatus.UNKNOWN}
        });

        // Log current pending batch size
        logDebug('State manager: Current pending batch size:', this.#pendingBatch.size);

        // Schedule batch processing
        logDebug('State manager: Scheduling batch processing');
        this.#scheduleBatchProcessing();
    }

    #scheduleBatchProcessing(): void {
        logDebug('State manager: Scheduling batch processing with delay:', BatchConfig.batchDelay);
        
        if (this.#batchProcessingTimeout) {
            logDebug('State manager: Clearing existing batch timeout');
            clearTimeout(this.#batchProcessingTimeout);
        }
        
        this.#batchProcessingTimeout = setTimeout(async () => {
            logDebug('State manager: Batch timeout fired, processing batch');
            await this.#processBatch();
        }, BatchConfig.batchDelay);
    }

    async #processBatch(): Promise<void> {
        logDebug('State manager: Starting batch processing');
        logDebug('State manager: Current pending batch:', Array.from(this.#pendingBatch));
        
        // Get next batch of jobs
        const batchJobs = Array.from(this.#pendingBatch).slice(0, BatchConfig.batchSize);
        if (batchJobs.length === 0) {
            logDebug('State manager: No jobs in batch to process');
            return;
        }

        logDebug('State manager: Processing batch jobs:', batchJobs);

        // Create jobInfo map for the batch
        const jobInfoMap = new Map<string, JobInfo>();
        batchJobs.forEach(jobId => {
            const state = this.getJobState(jobId);
            logDebug('State manager: Job state for batch job:', { jobId, state });
            if (state?.jobInfo) {
                jobInfoMap.set(jobId, state.jobInfo);
            }
        });

        logDebug('State manager: Created job info map:', Array.from(jobInfoMap.entries()));

        // Move jobs to processing
        batchJobs.forEach(jobId => {
            this.#pendingBatch.delete(jobId);
            this.#processingBatch.add(jobId);
        });

        logDebug('State manager: Moved jobs to processing batch');
        logDebug('State manager: Current processing batch:', Array.from(this.#processingBatch));

        // Schedule next batch if there are more pending
        if (this.#pendingBatch.size > 0) {
            logDebug('State manager: More jobs pending, scheduling next batch');
            this.#scheduleBatchProcessing();
        }

        // Process current batch
        try {
            logInfo('State manager: Calling filter service with batch');
            await this.#filterService.handleBatchPreliminaryFilter(batchJobs, jobInfoMap);
            logInfo('State manager: Filter service completed successfully');
        } catch (error) {
            logError('State manager: Error processing batch:', error);
            // Handle errors for each job in the batch
            batchJobs.forEach(jobId => {
                this.handleError(jobId, error instanceof Error ? error : new Error(String(error)));
            });
        } finally {
            // Clean up processing set
            batchJobs.forEach(jobId => {
                this.#processingBatch.delete(jobId);
            });
            logDebug('State manager: Cleaned up processing batch');
        }
    }

    async completeProcessing(jobId: string, status: JobStatus, jobStateData: Partial<JobStateData>): Promise<void> {
        this.#processingBatch.delete(jobId);
        this.#pendingBatch.delete(jobId);
        await this.updateJobState(jobId, JobState.COMPLETE, {
            ...jobStateData,
            filterResult: {
                ...jobStateData.filterResult,
                status: status
            }
        });
    }

    async handleError(jobId: string, error: Error): Promise<void> {
        this.#processingBatch.delete(jobId);
        this.#pendingBatch.delete(jobId);
        await this.updateJobState(jobId, JobState.ERROR, {
            filterResult: {status:JobStatus.UNKNOWN},
            tooltip: error.message
        });
    }

    async handleDetailedFiltering(jobId: string, jobInfo: JobInfo): Promise<void> {
        logDebug('Handling detailed filtering for job:', { jobId, jobInfo });

        // Check if already processing or complete
        if (this.isProcessing(jobId)) {
            logDebug('Job is already being processed or is complete:', jobId);
            return;
        }

        // Get the current state
        const currentState = this.getJobState(jobId);

        // Update state to FILTERING, preserving existing filterResult
        await this.updateJobState(jobId, JobState.FILTERING, {
            jobInfo,
            filterResult: currentState?.filterResult || { status: JobStatus.UNKNOWN } // Preserve status if it exists
        });

        try {
            const detailedResult = await this.#filterService.handleDetailedFilter(jobId, jobInfo);
            logDebug('Detailed filtering result:', detailedResult);

            // Complete processing with the detailed result
            await this.completeProcessing(jobId, detailedResult.status, {
                tooltip: detailedResult.reasons?.join('\n'),
                filterResult: detailedResult // Update status with detailed result
            });
        } catch (error) {
            logError('Error during detailed filtering:', error);
            await this.handleError(jobId, error instanceof Error ? error : new Error(String(error)));
        }
    }

    async updateFromCache(jobId: string, result: FilterResult): Promise<void> {
        const currentState = this.getJobState(jobId);
        this.#jobStates.set(jobId, {
            state: JobState.COMPLETE,
            tooltip: result.reasons?.join('\n'),
            timestamp: new Date().toISOString(),
            jobInfo: currentState?.jobInfo,
            filterResult: result
        });
    }

    // Enhanced history management
    async addToHistory(jobId: string, historyEntry: JobHistoryEntry): Promise<void> {
        await this.#jobHistoryManager.updateJob(historyEntry)
    }

    async getFromHistory(jobId: string): Promise<Readonly<JobHistoryEntry> | undefined> {
        return await this.#jobHistoryManager.getJob(jobId);
    }
}