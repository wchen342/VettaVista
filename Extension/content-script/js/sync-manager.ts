import { logInfo, logWarn, enforceMethodRestriction } from "./debug";

export class SyncManager {
    private syncInProgress: boolean;
    private syncInterval: ReturnType<typeof setInterval> | null;

    constructor() {
        enforceMethodRestriction(
            'SyncManager',
            ['content-script.js'],
            ['content-script.js']);
        this.syncInProgress = false;
        this.syncInterval = null;
    }

    async startSync(intervalMs: number = 5 * 60 * 1000): Promise<void> { // Default 5 minutes
        logInfo('Starting sync manager');
        // Initial sync through background script
        await this.requestBackgroundSync();
        
        // Set up periodic sync through background script
        this.syncInterval = setInterval(() => {
            this.requestBackgroundSync();
        }, intervalMs);
    }

    stopSync(): void {
        logInfo('Stopping sync manager');
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
            this.syncInterval = null;
        }
    }

    private async requestBackgroundSync(): Promise<void> {
        if (this.syncInProgress) {
            logWarn('Sync already in progress, skipping');
            return;
        }

        try {
            this.syncInProgress = true;
            logInfo('Requesting background sync');

            // Request sync from background script
            await chrome.runtime.sendMessage({
                type: 'request_sync'
            });

            logInfo('Sync completed successfully');
        } catch (error) {
            console.error('Error syncing data:', error);
        } finally {
            this.syncInProgress = false;
        }
    }
} 