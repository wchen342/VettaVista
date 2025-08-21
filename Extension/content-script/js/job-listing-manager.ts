import {
    BatchConfig,
    BatchConfigType,
    JobHistoryEntry,
    JobInfo,
    JobState,
    JobStatus,
    ObserverConfig,
    Selectors
} from './constants';
import {LinkedInJobParser} from './linkedin-job-parser';
import {enforceMethodRestriction, logDebug, logError, logInfo, logWarn} from "./debug";
import {CacheService} from "./cache-service";
import {BlacklistManager} from "./blacklist-manager";
import {JobFilterService} from "./job-filter-service";
import {JobStateManager} from "./job-state-manager";
import {JobBoard} from "./job-boards";
import {JobHistoryManager} from "./job-history-manager";
import {JobApplicationManager} from "./job-application-manager";
import {JobUIManager} from "./job-ui-manager";

export class JobListingManager {
    // Private fields
    #jobListingObserver: MutationObserver = new MutationObserver(() => {});
    
    // Class fields for configuration
    #config: BatchConfigType = BatchConfig;

    #jobBoard: JobBoard;
    #cacheService: CacheService;
    #blacklistManager: BlacklistManager;
    #historyManager: JobHistoryManager;
    #filterService: JobFilterService;
    #stateManager: JobStateManager;
    #uiManager: JobUIManager;
    #applicationManager: JobApplicationManager;

    constructor(
        jobBoard: JobBoard,
        cacheService: CacheService,
        blacklistManager: BlacklistManager,
        historyManager: JobHistoryManager,
        filterService: JobFilterService,
        stateManager: JobStateManager,
        uiManager: JobUIManager,
        applicationManager: JobApplicationManager,
    ) {
        this.#jobBoard = jobBoard;
        this.#cacheService = cacheService;
        this.#blacklistManager = blacklistManager;
        this.#historyManager = historyManager;
        this.#filterService = filterService;
        this.#stateManager = stateManager;
        this.#uiManager = uiManager;
        this.#applicationManager = applicationManager;
    }

    // Static factory method
    static async create(
        jobBoard: JobBoard,
        cacheService: CacheService,
        blacklistManager: BlacklistManager,
        historyManager: JobHistoryManager,
        filterService: JobFilterService,
        stateManager: JobStateManager,
        uiManager: JobUIManager,
        applicationManager: JobApplicationManager,
    ): Promise<JobListingManager> {
        enforceMethodRestriction(
            'JobListingManager',
            ['content-script.js'],
            ['content-script.js']);
        const manager = new JobListingManager(
            jobBoard,
            cacheService,
            blacklistManager,
            historyManager,
            filterService,
            stateManager,
            uiManager,
            applicationManager
        );
        await manager.initialize();
        return manager;
    }

    // Async initialization method
    async initialize(): Promise<void> {
        // Initialize observer
        await this.#initializeObserver();

        // Start observing document root
        this.#jobListingObserver.observe(document.documentElement, ObserverConfig);

        // Process any existing listings
        await this.processJobListings();

        // Add UI elements
        this.addLegend();

        // Subscribe to state changes
        this.#stateManager.subscribe(async (jobId, state) => {
            const jobListing = this.#jobBoard.findJobListingById(jobId);
            if (!jobListing) return;

            // Update UI based on state
            if (state.state === JobState.COMPLETE) {
                logDebug(`Job state of id ${jobId} changed, now COMPLETE`);
                this.#jobBoard.updateJobCardStatus(jobListing, state.filterResult.status);
                if (state.tooltip) {
                    this.#jobBoard.setJobCardTooltip(jobListing, state.tooltip);
                }
                await this.updateProcessingUI(jobListing, false);
            } else if (state.state === JobState.ERROR) {
                logDebug(`Job state of id ${jobId} changed, now ERROR`);
                // For error state, use UNKNOWN visual status but show error tooltip
                this.#jobBoard.updateJobCardStatus(jobListing, JobStatus.UNKNOWN);
                this.#jobBoard.setJobCardTooltip(jobListing, state.tooltip || 'An error occurred');
                await this.updateProcessingUI(jobListing, false);
            } else if (state.state === JobState.FILTERING) {
                logDebug(`Job state of id ${jobId} changed, now FILTERING`);
                await this.updateProcessingUI(jobListing, true);
            }
        });

        // Subscribe to filter completion to update cacheService
        this.#filterService.onFilterComplete((jobId, result) => {
            if (result.status !== JobStatus.UNKNOWN) {
                this.#cacheService.setFilterResult(jobId, result);
            }
        });

        // Subscribe to blacklist changes
        this.#blacklistManager.subscribe(async (company, action) => {
            // Only reprocess listings from the affected company
            logInfo(`Reprocessing listings for company ${company} due to blacklist ${action}`);
            if (action === 'remove') {
                const jobListings = this.#jobBoard.getJobListings();

                // Get all listings with this company name in parallel
                const processingPromises = Array.from(jobListings).map(async (listing) => {
                    // Get job info for this specific listing
                    const jobInfo = await LinkedInJobParser.getBasicJobInfo(listing);

                    // If it's a valid unprocessed job, process it immediately
                    if (jobInfo && jobInfo.jobId && jobInfo?.company === company && !this.#stateManager.isProcessing(jobInfo.jobId)) {
                        await this.processJobListing(listing, jobInfo);
                    }
                });

                await Promise.all(processingPromises);
            }
        });

        // Enhanced click handler for job cards and apply buttons
        document.addEventListener('click', async (event: MouseEvent) => {
            const target = event.target as Element;
            
            // Handle apply button clicks
            const applyButton = target.closest(Selectors.APPLY_BUTTON);
            if (applyButton) {
                try {
                    logInfo('Apply button clicked');
                    await this.#applicationManager.handleApplyButtonClick(applyButton as HTMLElement);
                } catch (error) {
                    logError('Error in apply button click handler:', error);
                }
                return;
            }

            // Handle job card clicks
            const jobCard = target.closest('[data-job-id], [data-entity-urn]');
            if (!jobCard) return;
            const jobInfo = await LinkedInJobParser.getDetailedJobInfo(jobCard);
            const jobId = jobInfo?.jobId;
            if (!jobId) return;

            // Let LinkedIn handle the click first
            setTimeout(async () => {
                await this.#stateManager.handleDetailedFiltering(jobId, jobInfo);
            }, 500); // Wait for LinkedIn to update the UI
        });
    }

    #initializeObserver(): void {
        if (this.#jobListingObserver) {
            this.#jobListingObserver.disconnect();
        }

        // Observer that focuses on content elements rather than structure
        this.#jobListingObserver = new MutationObserver(async (mutations) => {
            // Check for specific content elements being added that indicate job listings
            const hasRelevantChanges = mutations.some(mutation => {
                // Only care about element additions
                if (mutation.type !== 'childList' || mutation.addedNodes.length === 0) {
                    return false;
                }

                // Look for specific content elements rather than structure
                return Array.from(mutation.addedNodes).some(node => {
                    if (node.nodeType !== Node.ELEMENT_NODE) return false;
                    const element = node as Element;

                    // Check if this element is one of our target elements
                    const isJobElement =
                        // Direct job card addition
                        element.matches?.(Selectors.JOB_CARD) ||

                        // Job title addition - key indicator of job content
                        element.matches?.(Selectors.TITLE) ||
                        element.querySelector?.(Selectors.TITLE) ||

                        // Company name addition - also key indicator
                        element.matches?.(Selectors.COMPANY_NAME_DIV) ||
                        element.querySelector?.(Selectors.COMPANY_NAME_DIV) ||

                        // Job location addition
                        element.matches?.(Selectors.LOCATION_DIV) ||
                        element.querySelector?.(Selectors.LOCATION_DIV) ||

                        // Any element with job-id (most reliable indicator)
                        element.matches?.(Selectors.JOB_CARD) ||
                        element.querySelector?.(Selectors.JOB_CARD);

                    return isJobElement;
                });
            });

            if (hasRelevantChanges) {
                logDebug('Relevant job content detected, processing job listings');
                await this.processJobListings();
            }
        });

        // Observe the entire document to catch all content changes
        // This is more resilient to structural changes
        this.#jobListingObserver.observe(document.documentElement, ObserverConfig);
    }

    async processJobListings(): Promise<void> {
        const jobListings = this.#jobBoard.getJobListings();
        logInfo('Processing job listings:', jobListings.length);

        // Create an array of promises, each handling a complete listing process
        const processingPromises = Array.from(jobListings).map(async (listing) => {
            // Get job info for this specific listing
            const jobInfo = await LinkedInJobParser.getBasicJobInfo(listing);

            // If it's a valid unprocessed job, process it immediately
            if (jobInfo && jobInfo.jobId && !this.#stateManager.isProcessing(jobInfo.jobId)) {
                logDebug('Processing unprocessed listing:', jobInfo.jobId);
                await this.processJobListing(listing, jobInfo);
            }
        });

        // Wait for all independent processing flows to complete
        await Promise.all(processingPromises);

        this.updateStats();
    }

    async processJobListing(jobListing: Element, jobInfo: JobInfo): Promise<void> {
        if (!jobInfo?.jobId) {
            logWarn('No job ID found for listing:', jobListing);
            return;
        }

        if (this.#stateManager.isProcessing(jobInfo.jobId)) {
            logDebug('Job is already being processed:', jobInfo.jobId);
            return;
        }

        // Set hidden
        // Get current hide-filtered state
        const { hideFiltered = false } = await chrome.storage.local.get('hideFiltered');

        // Update parent li element's hide-filtered class
        const parentLi = jobListing.closest(Selectors.JOB_LIST_ITEM);
        if (parentLi) {
            this.#uiManager.setJobCardHiddenState(parentLi, hideFiltered);
        }

        logDebug('Processing job listing:', jobInfo);

        try {
            // Check blacklist
            logDebug('Checking blacklist for company:', jobInfo.company);
            if (await this.#blacklistManager.isCompanyBlacklisted(jobInfo.company)) {
                logInfo('Company is blacklisted:', jobInfo.company);
                this.#jobBoard.setJobCardTooltip(jobListing, 'Company is blacklisted');
                this.#jobBoard.updateJobCardBlacklistStatus(jobListing, true);
                await this.updateProcessingUI(jobListing, false); // Clear processing UI
                return;
            } else {
                this.#jobBoard.updateJobCardBlacklistStatus(jobListing, false);
            }

            // Check history
            logDebug('Checking history for job:', jobInfo.jobId);
            const historyEntry = await this.#historyManager.getJob(jobInfo.jobId);
            if (historyEntry) {
                logDebug('Job found in history:', historyEntry);
                this.#jobBoard.updateJobCardStatus(jobListing, historyEntry.match_status);
                if (historyEntry.skip_reason) {
                    this.#jobBoard.setJobCardTooltip(jobListing, historyEntry.skip_reason);
                }
                this.#jobBoard.updateJobCardApplicationStatus(jobListing, historyEntry.application_status);
                await this.updateProcessingUI(jobListing, false); // Clear processing UI
                return;
            }

            // Check filter cacheService
            logDebug('Checking cacheService for job:', jobInfo.jobId);
            const cachedResult = this.#cacheService.getFilterResult(jobInfo.jobId);
            if (cachedResult && cachedResult.status !== JobStatus.UNKNOWN && cachedResult.status !== JobStatus.ERROR) {
                logDebug('Found cached filter result:', cachedResult);
                this.#jobBoard.updateJobCardStatus(jobListing, cachedResult.status);
                if (cachedResult.reasons) {
                    this.#jobBoard.setJobCardTooltip(jobListing, cachedResult.reasons.join('\n'));
                }
                await this.updateProcessingUI(jobListing, false); // Clear processing UI
                return;
            }

            // Preliminary filtering with retries
            logInfo('Starting preliminary filtering for job:', jobInfo.jobId);
            try {
                let retries = 0;
                while (retries < this.#config.maxRetries) {
                    try {
                        logDebug(`Attempt ${retries + 1} to add job to filter batch:`, jobInfo.jobId);
                        await this.#stateManager.addToBatch(jobInfo.jobId, jobInfo);
                        logInfo('Successfully processed job:', jobInfo.jobId);
                        break;
                    } catch (error: any) {
                        if (error.message === 'Job is already being processed') {
                            break;
                        } else {
                            retries++;
                            logWarn(`Filter attempt ${retries} failed for job ${jobInfo.jobId}:`, error);
                            if (retries === this.#config.maxRetries) {
                                throw error;
                            }
                            await new Promise(resolve => setTimeout(resolve, this.#config.retryDelay));
                        }
                    }
                }
            } catch (error) {
                logError('All retry attempts failed for preliminary filtering:', error);
                throw error;
            }
        } catch (error) {
            logError('Error processing job listing:', error);
            this.#jobBoard.updateJobCardStatus(jobListing, JobStatus.UNKNOWN);
            this.#jobBoard.setJobCardTooltip(jobListing, `Error: ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    addLegend(): void {
        const legend = document.createElement('div');
        legend.className = 'job-status-legend';
        legend.innerHTML = `
            <div class="legend-title">Job Match Status</div>
            <div class="legend-item" data-status="${JobStatus.UNKNOWN}">
                <span class="indicator"></span>Not analyzed
            </div>
            <div class="legend-item" data-status="${JobStatus.LIKELY_MATCH}">
                <span class="indicator"></span>Likely match
            </div>
            <div class="legend-item" data-status="${JobStatus.POSSIBLE_MATCH}">
                <span class="indicator"></span>Possible match
            </div>
            <div class="legend-item" data-status="${JobStatus.NOT_LIKELY}">
                <span class="indicator"></span>Not likely
            </div>
            <div class="legend-item" data-status="${JobStatus.CONFIRMED_MATCH}">
                <span class="indicator"></span>Confirmed match
            </div>
            <div class="legend-item" data-status="${JobStatus.CONFIRMED_NO_MATCH}">
                <span class="indicator"></span>Confirmed no match
            </div>
            <div class="legend-item" data-status="${JobStatus.ERROR}">
                <span class="indicator"></span>Error
            </div>
            <div class="legend-item" data-status="${JobState.BLACKLISTED}">
                <span class="indicator"></span>Blacklisted company
            </div>
            <div class="stats"></div>
        `;
        
        // Insert after the filters section
        const filtersSection = document.querySelector('.jobs-search-box-container');
        if (filtersSection) {
            filtersSection.parentNode?.insertBefore(legend, filtersSection.nextSibling);
        }
    }

    updateStats(): void {
        const stats = {
            total: 0,
            unknown: 0,
            likely_match: 0,
            possible_match: 0,
            not_likely: 0,
            confirmed_match: 0,
            confirmed_no_match: 0,
            blacklisted: 0
        };
        
        // Collect stats from visible job listings
        const jobListings = this.#jobBoard.getJobListings();
        jobListings.forEach(listing => {
            const jobCard = listing.querySelector(Selectors.JOB_CARD);
            if (jobCard) {
                const status = (jobCard as HTMLElement).dataset.status || JobStatus.UNKNOWN;
                stats.total++;
                stats[status as keyof typeof stats]++;
            }
        });
        
        // Update stats display
        const statsDiv = document.querySelector('.job-status-legend .stats');
        if (statsDiv) {
            statsDiv.textContent = `Found ${stats.likely_match + stats.confirmed_match} potential matches out of ${stats.total} jobs (${stats.blacklisted} blacklisted)`;
        }
    }

    async updateProcessingUI(jobListing: Element, isProcessing: boolean): Promise<void> {
        const jobInfo = await LinkedInJobParser.getBasicJobInfo(jobListing);
        logDebug('Updating processing UI:', { jobId: jobInfo?.jobId, isProcessing });
        if (isProcessing) {
            const indicator = document.createElement('div');
            indicator.className = 'job-processing-indicator';
            indicator.innerHTML = '<div class="spinner"></div>';
            jobListing.appendChild(indicator);
        } else {
            const indicator = jobListing.querySelector('.job-processing-indicator');
            if (indicator) {
                indicator.remove();
            }
        }
    }

    async updateJobApplication(jobData: JobHistoryEntry): Promise<void> {
        try {
            // Get the job listing element
            const jobListing = this.#jobBoard.findJobListingById(jobData.job_id);
            if (!jobListing) {
                logWarn('Job listing not found for update:', jobData.job_id);
                return;
            }

            // Update job history through history manager
            await this.#historyManager.updateJob({
                job_id: jobData.job_id,
                title: jobData.title,
                company: jobData.company,
                location: jobData.location,
                url: jobData.url,
                match_status: jobData.match_status,
                application_status: jobData.application_status,
                user_notes: jobData.user_notes,
                cover_letter_path: jobData.cover_letter_path,
                date_applied: jobData.date_applied,
                date_created: jobData.date_created,
                date_updated: jobData.date_updated,
                date_rejected: jobData.date_rejected,
                skip_reason: jobData.skip_reason,
                resume_path: jobData.resume_path,
                rejection_reason: jobData.rejection_reason
            });

            // Update UI
            this.#jobBoard.updateJobCardStatus(jobListing, jobData.match_status);
            if (jobData.skip_reason) {
                this.#jobBoard.setJobCardTooltip(jobListing, jobData.skip_reason);
            }

            // Update stats display
            this.updateStats();

        } catch (error) {
            logError('Error updating job application:', error);
            throw error;
        }
    }
} 