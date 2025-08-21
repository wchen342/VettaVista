/**
 * Gets all tabs in the current window
 * @returns Promise that resolves with a Tab objects
 */
function getActiveTabsInCurrentWindow(): Promise<chrome.tabs.Tab | undefined> {
    return new Promise((resolve, reject) => {
        chrome.tabs.query({
            active: true,
            currentWindow: true,
        }, (tabs) => {
            if (chrome.runtime.lastError) {
                reject(chrome.runtime.lastError);
            } else {
                resolve(tabs[0]);
            }
        });
    });
}

// Message type for hide filtered toggle
interface HideFilteredMessage {
    type: 'toggle_hide_filtered';
    hideFiltered: boolean;
}

interface CheckJobBoardMessage {
    type: 'check_job_board';
}

interface JobBoardResponse {
    isJobBoard: boolean;
}

class PopupManager {
    private hideFilteredCheckbox: HTMLInputElement;

    constructor() {
        this.hideFilteredCheckbox = document.querySelector('input[name="hide-filtered"]') as HTMLInputElement;
        this.initializePopup();
    }

    private async initializePopup() {
        // Check if current tab is a job board
        const tab = await getActiveTabsInCurrentWindow();
        if (!tab) return;  // Early return if no tab
        
        const isJobBoard = await this.checkIfJobBoard(tab);
        
        // Set visibility mode
        document.documentElement.setAttribute('data-tab-is-job-board', isJobBoard.toString());

        // Initialize checkbox if on job board
        if (isJobBoard) {
            await this.initializeCheckbox();
        }
    }

    private async checkIfJobBoard(tab: chrome.tabs.Tab): Promise<boolean> {
        if (!tab?.id) return false;
        try {
            const response = await chrome.tabs.sendMessage<CheckJobBoardMessage, JobBoardResponse>(
                tab.id,
                { type: 'check_job_board' }
            );
            return response?.isJobBoard ?? false;
        } catch {
            return false;
        }
    }

    private async initializeCheckbox() {
        // Get current state from storage
        const { hideFiltered = false } = await chrome.storage.local.get('hideFiltered');
        this.hideFilteredCheckbox.checked = hideFiltered;
        this.updateCheckboxLabel();

        // Add change listener
        this.hideFilteredCheckbox.addEventListener('change', async () => {
            // Save state - this will trigger storage.onChanged which content script listens to
            await chrome.storage.local.set({ 
                hideFiltered: this.hideFilteredCheckbox.checked 
            });
            this.updateCheckboxLabel();
        });
    }

    private updateCheckboxLabel() {
        const label = this.hideFilteredCheckbox.closest('.toggle-container');
        if (label) {
            label.setAttribute('data-checked', this.hideFilteredCheckbox.checked.toString());
        }
    }
}

// Initialize popup
document.addEventListener('DOMContentLoaded', () => {
    new PopupManager();
}); 