import {enforceMethodRestriction} from "./debug";
import {ApplicationStatus, JobHistoryEntry, jobIdType} from "./constants";

type JobHistorySubscriber = (jobHistories: JobHistoryEntry[]) => void;

export class JobHistoryManager {
    #subscribers = new Set<JobHistorySubscriber>();
    #storageUpdateResolvers: ((value: void) => void)[] = [];

    constructor() {
        enforceMethodRestriction(
            'JobHistoryManager',
            ['job-state-manager.js', 'job-listing-manager.js'],
            ['content-script.js']);

        // Single listener for all storage changes
        chrome.storage.onChanged.addListener((changes) => {
            if (changes.job_history) {
                this.#notifySubscribers(changes.job_history as JobHistoryEntry[]);

                // Resolve and clear all pending resolvers
                const resolvers = [...this.#storageUpdateResolvers];
                this.#storageUpdateResolvers = [];  // Clear the array
                resolvers.forEach(resolve => resolve());
            }
        });
    }

    subscribe(callback: JobHistorySubscriber): () => void {
        this.#subscribers.add(callback);
        return () => this.#subscribers.delete(callback);
    }

    #notifySubscribers(jobHistories: JobHistoryEntry[]): void {
        this.#subscribers.forEach(callback => {
            try {
                callback(jobHistories);
            } catch (error) {
                console.error('Error in blacklist subscriber:', error);
            }
        });
    }

    private async waitForStorageUpdate(): Promise<void> {
        return new Promise<void>((resolve) => {
            this.#storageUpdateResolvers.push(resolve);
        });
    }

    async updateJob(jobData: Partial<JobHistoryEntry>): Promise<void> {
        try {
            const response = await chrome.runtime.sendMessage({
                type: 'update_job_history',
                data: jobData
            });

            if (response?.status === 'error') {
                throw new Error(response.error);
            }

            await this.waitForStorageUpdate();
        } catch (error) {
            console.error('Error updating job history:', error);
            throw error;
        }
    }

    async getJob(job_id: jobIdType): Promise<Readonly<JobHistoryEntry> | undefined> {
        const { job_history } = await chrome.storage.local.get('job_history');
        return Array.isArray(job_history) ? job_history.find(entry => entry.job_id === job_id) : undefined;
    }

    async getAllJobs(): Promise<ReadonlyArray<JobHistoryEntry>> {
        const { job_history } = await chrome.storage.local.get('job_history');
        return Array.isArray(job_history) ? job_history : [];
    }

    async updateApplicationStatus(job_id: jobIdType, status: ApplicationStatus, notes: string = ""): Promise<void> {
        try {
            await this.updateJob({
                job_id: job_id,
                application_status: status,
                user_notes: notes
            });
        } catch (error) {
            console.error('Error updating application status:', error);
            throw error;
        }
    }
} 