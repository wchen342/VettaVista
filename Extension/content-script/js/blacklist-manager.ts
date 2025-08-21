import {enforceMethodRestriction, logInfo} from "./debug";

type BlacklistSubscriber = (company: string, action: 'add' | 'remove', metadata: { reason?: string }) => void;

export class BlacklistManager {
    #subscribers = new Set<BlacklistSubscriber>();
    #storageUpdateResolvers: ((value: void) => void)[] = [];

    constructor() {
        enforceMethodRestriction(
            'BlacklistManager',
            ['job-state-manager.js', 'job-listing-manager.js'],
            ['content-script.js']);

        // Single listener for all storage changes
        chrome.storage.onChanged.addListener((changes) => {
            if (changes.blacklist) {
                // Resolve and clear all pending resolvers
                const resolvers = [...this.#storageUpdateResolvers];
                this.#storageUpdateResolvers = [];  // Clear the array
                resolvers.forEach(resolve => resolve());
            }
        });
    }

    private async waitForStorageUpdate(): Promise<void> {
        return new Promise<void>((resolve) => {
            this.#storageUpdateResolvers.push(resolve);
        });
    }

    subscribe(callback: BlacklistSubscriber): () => void {
        this.#subscribers.add(callback);
        return () => this.#subscribers.delete(callback);
    }

    #notifySubscribers(company: string, action: 'add' | 'remove', metadata: { reason?: string } = {}): void {
        this.#subscribers.forEach(callback => {
            try {
                callback(company, action, metadata);
            } catch (error) {
                console.error('Error in blacklist subscriber:', error);
            }
        });
    }

    async isCompanyBlacklisted(company: string): Promise<boolean> {
        const { blacklist } = await chrome.storage.local.get('blacklist');
        return Array.isArray(blacklist) && blacklist.some(entry => entry.company === company);
    }

    async addCompany(company: string, reason?: string): Promise<void> {
        logInfo('Adding company to blacklist:', company);
        
        try {
            // Send message through background.ts
            const response = await chrome.runtime.sendMessage({
                type: 'add_to_blacklist',
                data: { company, reason }
            });

            if (response?.status === 'error') {
                throw new Error(response.error);
            }

            // Wait for storage update
            await this.waitForStorageUpdate();
            this.#notifySubscribers(company, 'add', { reason });
        } catch (error) {
            console.error('Error adding company to blacklist:', error);
            throw error;
        }
    }

    async removeCompany(company: string): Promise<void> {
        logInfo('Removing company from blacklist:', company);
        
        try {
            const response = await chrome.runtime.sendMessage({
                type: 'remove_from_blacklist',
                data: { company }
            });

            if (response?.status === 'error') {
                throw new Error(response.error);
            }

            await this.waitForStorageUpdate();
            this.#notifySubscribers(company, 'remove');
        } catch (error) {
            console.error('Error removing company from blacklist:', error);
            throw error;
        }
    }
} 