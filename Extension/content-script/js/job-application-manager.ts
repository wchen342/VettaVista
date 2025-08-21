import { enforceMethodRestriction, logDebug, logInfo, logError } from './debug';
import { MessageTypes } from './constants';

export class JobApplicationManager {
    constructor() {
        enforceMethodRestriction(
            'JobApplicationManager',
            ['content-script.js'],
            ['content-script.js']
        );
    }

    private getJobIdFromUrl(): string | null {
        const match = location.href.match(/currentJobId=(\d+)/);
        return match?.[1] ?? null;
    }

    private getJobIdFromSelectedCard(): string | null {
        // Look for the active job card
        const selectedCard = document.querySelector(
            'li.scaffold-layout__list-item.jobs-search-results-list__list-item--active, ' +
            'li.occludable-update.jobs-search-results-list__list-item--active'
        );
        
        if (!selectedCard) {
            return null;
        }

        // Try getting ID from data attribute
        return selectedCard.getAttribute('data-occludable-job-id');
    }

    private getApplyButtonType(button: Element): 'easy_apply' | 'external' {
        const isEasyApply = button.getAttribute('aria-label')?.toLowerCase().includes('easy apply') ||
            button.textContent?.toLowerCase().includes('easy apply');
        return isEasyApply ? 'easy_apply' : 'external';
    }

    async handleApplyButtonClick(applyButton: HTMLElement): Promise<void> {
        try {
            logInfo('Processing apply button click');
            let jobId = applyButton.getAttribute('data-job-id');

            // If jobId not provided (non-Easy Apply), try to get it
            if (!jobId) {
                // First try URL
                jobId = this.getJobIdFromUrl();
                
                // If not in URL, try selected card
                if (!jobId) {
                    jobId = this.getJobIdFromSelectedCard();
                }

                if (!jobId) {
                    throw new Error('Could not determine job ID');
                }
            }

            logDebug('Find Job ID for Apply button:', jobId);

            // Determine apply button type
            const applyType = this.getApplyButtonType(applyButton);
            logDebug('Apply button type:', applyType);

            // Send message to background script
            const response = await chrome.runtime.sendMessage({
                type: MessageTypes.HANDLE_APPLY,
                data: {
                    jobId,
                    applyType,
                    timestamp: Date.now()
                }
            });

            if (response?.editor_url) {
                window.open(response.editor_url, '_blank');
            }
        } catch (error) {
            logError('Error handling apply button click:', error);
            throw error;
        }
    }
} 