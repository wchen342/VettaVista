import {JobHistoryEntry, jobIdType, JobState, JobStateData, Selectors} from './constants';
import {enforceMethodRestriction} from "./debug";
import {LinkedInJobParser} from "./linkedin-job-parser";
import {JobStateManager} from "./job-state-manager";
import {JobHistoryManager} from "./job-history-manager";
import {JobBoard} from "./job-boards";

export class JobUIManager {
    private jobBoard: JobBoard;
    private stateManager: JobStateManager;
    private historyManager: JobHistoryManager;
    private hideFiltered: boolean = false;

    constructor(
        jobBoard: JobBoard,
        stateManager: JobStateManager,
        historyManager: JobHistoryManager) {
        enforceMethodRestriction(
            'JobUIManager',
            ['job-state-manager.js'],
            ['content-script.js']
        );
        this.jobBoard = jobBoard;
        this.stateManager = stateManager;
        this.historyManager = historyManager;

        // Subscribe to job history changes
        this.historyManager.subscribe((jobHistories: JobHistoryEntry[]) => {
            jobHistories.forEach((jobHistory: JobHistoryEntry) => {
                const jobElement = this.jobBoard.findJobListingById(jobHistory.job_id);
                if (!jobElement) return;

                this.jobBoard.updateJobCardApplicationStatus(jobElement, jobHistory.application_status);
            })
        })

        // Subscribe to state changes
        this.stateManager.subscribe(async (jobId: jobIdType, state: JobStateData) => {
            const jobElement = this.jobBoard.findJobListingById(jobId);
            if (!jobElement) return;

            // Get current hide-filtered state
            const { hideFiltered = false } = await chrome.storage.local.get('hideFiltered');

            // Update parent li element's hide-filtered class
            const parentLi = jobElement.closest(Selectors.JOB_LIST_ITEM);
            if (parentLi) {
                this.setJobCardHiddenState(parentLi, hideFiltered);
            }

            // Continue with other state updates
            this.handleStateChange(jobId, state);
        });

        // Add blacklist buttons to existing cards
        this.addBlacklistButtonsToExistingCards();

        // Only listen for changes, don't apply initial state here
        chrome.storage.onChanged.addListener((changes) => {
            if ('hideFiltered' in changes) {
                const hideFiltered = changes.hideFiltered?.newValue;
                // Update all existing jobs when setting changes
                const jobListItems = this.jobBoard.getJobListings();
                jobListItems.forEach(item => {
                    if (hideFiltered) {
                        this.setJobCardHiddenState(item, true);
                    } else {
                        this.setJobCardHiddenState(item, false);
                    }
                });
            }
        });

        // Initialize storage state
        chrome.storage.local.get('hideFiltered').then(({ hideFiltered = false }) => {
            this.hideFiltered = hideFiltered;
        });

        // Listen for messages from popup
        chrome.runtime.onMessage.addListener((message: { type: string; hideFiltered?: boolean }) => {
            if (message.type === 'toggle_hide_filtered' && message.hideFiltered !== undefined) {
                chrome.storage.local.set({ hideFiltered: message.hideFiltered });
            }
        });
    }

    setJobCardHiddenState = (element: Element, hideFiltered: boolean) => {
        if (hideFiltered) {
            element.classList.add('hide-filtered');
        } else {
            element.classList.remove('hide-filtered');
        }
    }

    private handleStateChange(jobId: jobIdType, state: JobStateData): void {
        const jobElement = this.jobBoard.findJobListingById(jobId);
        if (!jobElement) return;

        // Update visual status
        this.jobBoard.updateJobCardStatus(jobElement, state.filterResult.status);
        
        // Update processing indicator
        this.updateProcessingUI(jobElement, state.state === JobState.FILTERING);
        
        // Update tooltip if available
        if (state.tooltip) {
            this.jobBoard.setJobCardTooltip(jobElement, state.tooltip);
        }

        // Add blacklist button if not present
        this.addBlacklistButton(jobElement);
    }

    private updateProcessingUI(jobElement: Element, isProcessing: boolean): void {
        // If jobElement is itself the job-card-container, we need its parent
        const containerParent = jobElement.classList.contains('job-card-container') 
            ? jobElement.parentElement 
            : jobElement;
            
        if (!containerParent) return;
        
        const existingIndicator = containerParent.querySelector('.job-processing-indicator');
        
        if (isProcessing && !existingIndicator) {
            const indicator = document.createElement('div');
            indicator.className = 'job-processing-indicator';
            indicator.innerHTML = '<div class="spinner"></div>';
            containerParent.appendChild(indicator);
        } else if (!isProcessing && existingIndicator) {
            existingIndicator.remove();
        }
    }

    private addBlacklistButtonsToExistingCards(): void {
        const jobCards = document.querySelectorAll(Selectors.JOB_CARD);
        jobCards.forEach(card => this.addBlacklistButton(card));
    }

    private addBlacklistButton(jobCard: Element): void {
        if (jobCard.querySelector(Selectors.BLACKLIST_BUTTON)) return; // Don't add if already exists

        const button = document.createElement('button');
        button.className = Selectors.BLACKLIST_BUTTON.slice(1);
        button.innerHTML = '⊖';
        button.title = 'Blacklist Company';

        button.addEventListener('click', async (e: MouseEvent) => {
            e.preventDefault();
            e.stopPropagation();
            
            const jobId = jobCard.getAttribute('data-job-id') || jobCard.getAttribute('data-occludable-job-id');
            if (!jobId) return;

            // Get company name from the card
            const companyElement = jobCard.querySelector(Selectors.COMPANY_NAME_OR_JOB_INFO);
            if (!companyElement) return;

            const {company} = LinkedInJobParser.getNameLocationFromCompanyElement(companyElement);
            if (!company) return;

            // Use StateManager to handle blacklist operation
            try {
                await this.stateManager.handleBlacklistButtonClick(jobId, company);
            } catch (error) {
                console.error('Error handling blacklist button click:', error);
            }
        });

        (jobCard as HTMLElement).style.position = 'relative';
        jobCard.appendChild(button);
    }
} 