import {
    DetailedFilterResult,
    JobHistoryEntry, jobIdType,
    MessageTypes,
    PreliminaryFilterResult
} from "../../content-script/js/constants";

const API_BASE_URL = '127.0.0.1:8000';   // Locked to localhost
const REST_API_BASE_URL = `http://${API_BASE_URL}`;
const WS_BASE_URL = `ws://${API_BASE_URL}`;

class WebSocketClient {
    private ws: WebSocket | null;
    private readonly clientId: string;
    private isConnected: boolean;
    private pendingMessages: any[];

    constructor() {
        this.ws = null;
        this.clientId = crypto.randomUUID();
        this.isConnected = false;
        this.pendingMessages = [];
        this.connect();
    }

    connect() {
        try {
            this.ws = new WebSocket(`${WS_BASE_URL}/ws/sync/${this.clientId}`);

            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.isConnected = true;
                
                // Process any pending messages
                while (this.pendingMessages.length > 0) {
                    const {type, data} = this.pendingMessages.shift();
                    this.sendMessage(type, data);
                }
            };

            this.ws.onmessage = async (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('Received message from server:', data);

                    if (data.type === "stats_response") {
                        console.log('Received stats:', data.data);
                    } else if (data.type === "sync_response") {
                        // Handle sync data uniformly
                        const storage = await chrome.storage.local.get();
                        let updatedStorage = {...storage};

                        // Update blacklist if provided
                        if (data.data.blacklist !== undefined) {
                            updatedStorage.blacklist = data.data.blacklist;
                        }

                        // Update history if provided
                        if (data.data.history !== undefined) {
                            updatedStorage.job_history = data.data.history;
                        }

                        await chrome.storage.local.set(updatedStorage);
                        console.log('Synced with server:', {
                            blacklist: updatedStorage.blacklist?.length ?? 0,
                            history: updatedStorage.job_history?.length ?? 0
                        });
                    }
                } catch (error) {
                    console.error('Error processing WebSocket message:', error);
                }
            };

            this.ws.onclose = (event) => {
                console.log('Disconnected from Python server:', event.code, event.reason);
                this.isConnected = false;
                // Only attempt to reconnect if it wasn't a normal closure
                if (event.code !== 1000 && event.code !== 1001) {
                    console.log('Attempting to reconnect in 5 seconds...');
                    setTimeout(() => this.connect(), 5000);
                }
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.isConnected = false;
            };
        } catch (error) {
            console.error('Error connecting to WebSocket:', error);
            this.isConnected = false;
        }
    }

    sendMessage(type: any, data: any) {
        if (!this.isConnected) {
            console.log('WebSocket not connected, queueing message:', type);
            this.pendingMessages.push({type, data});
            return false;
        }

        try {
            if (!this.ws) {
                throw new Error('WebSocket is not initialized');
            }

            this.ws.send(JSON.stringify({
                type: type,
                data: data
            }));
            return true;
        } catch (error) {
            console.error('Error sending message:', error);
            return false;
        }
    }
}

const wsClient = new WebSocketClient();

class ServerConnection {
    static SYNC_INTERVAL = 5 * 60 * 1000; // 5 minutes
    static syncInProgress = false;
    static lastSyncTime = 0;
    static MIN_SYNC_INTERVAL = 30 * 1000; // 30 seconds minimum between syncs

    static async initialize() {
        // Initial sync on startup
        await this.syncWithServer();

        // Set up periodic sync
        setInterval(() => this.syncWithServer(), this.SYNC_INTERVAL);

        // Listen for network connectivity changes
        chrome.runtime.onStartup.addListener(() => this.debouncedSync());
        chrome.runtime.onInstalled.addListener(() => this.debouncedSync());
    }

    static async debouncedSync() {
        if (this.syncInProgress) {
            console.log('Skipping sync - sync in progress');
            return;
        }
        await this.syncWithServer();
    }

    static async syncWithServer() {
        if (this.syncInProgress) {
            console.log('Sync already in progress, skipping');
            return;
        }

        try {
            this.syncInProgress = true;
            console.log('Starting server sync');

            // Use WebSocket for sync instead of REST API
            wsClient.sendMessage('sync_request', {});
            this.lastSyncTime = Date.now();

        } catch (error) {
            console.error('Server sync failed:', error);
        } finally {
            this.syncInProgress = false;
        }
    }

    // Server update methods
    static async addToBlacklist(company: string, reason = '', notes = '') {
        try {
            const response = await fetch(`${REST_API_BASE_URL}/api/blacklist`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({company, reason, notes})
            });

            if (!response.ok) throw new Error('Failed to add to blacklist');
            await this.debouncedSync(); // Get updated lists
        } catch (error) {
            console.error('Failed to add to blacklist:', error);
            throw error;
        }
    }

    static async removeFromBlacklist(company: string) {
        try {
            const response = await fetch(`${REST_API_BASE_URL}/api/blacklist/${encodeURIComponent(company)}`, {
                method: 'DELETE'
            });

            if (!response.ok) throw new Error('Failed to remove from blacklist');
            await this.debouncedSync(); // Get updated lists
        } catch (error) {
            console.error('Failed to remove from blacklist:', error);
            throw error;
        }
    }

    static async updateJobHistory(jobData: JobHistoryEntry) {
        try {
            const response = await fetch(`${REST_API_BASE_URL}/api/job-history`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(jobData)
            });

            if (!response.ok) throw new Error('Failed to update job history');
            await this.debouncedSync(); // Get updated lists
        } catch (error) {
            console.error('Failed to update job history:', error);
            throw error;
        }
    }

    static async handlePreliminaryFilter(jobDataList: PreliminaryFilterResult[]) {
        try {
            const response = await fetch(`${REST_API_BASE_URL}/api/preliminary-filter`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(jobDataList)
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            // Debug logs
            console.log('Raw response:', response);
            const jsonResponse = await response.json();
            console.log('Parsed response:', jsonResponse);
            return jsonResponse;
        } catch (error) {
            console.error('Failed to process preliminary filtering:', error);
            throw error;
        }
    }

    static async handleDetailedFilter(jobData: DetailedFilterResult) {
        try {
            const response = await fetch(`${REST_API_BASE_URL}/api/detailed-filter`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(jobData)
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return response.json();
        } catch (error) {
            console.error('Failed to process detailed filtering:', error);
            throw error;
        }
    }
}

async function handleApplyRequest(jobId: jobIdType, applyType: 'easy_apply' | 'external') {
    try {
        const response = await fetch(`${REST_API_BASE_URL}/api/apply/${jobId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ apply_type: applyType })
        });

        if (!response.ok) {
            throw new Error(`API request failed: ${response.status}`);
        }

        const data = await response.json();
        return {
            editor_url: `${REST_API_BASE_URL}${data.editor_url}`,
            claude_result: data.claude_result
        };
    } catch (error) {
        console.error('Error in apply request:', error);
        throw error;
    }
}

// Update the message handler
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // First check if this is an internal message
    if (message && message.to) {
        // This is an internal message
        if (!message.to.includes("background script")) return;
        // Process internal message...
        return;
    }

    // Handle application messages
    if (!message || typeof message !== 'object') {
        console.error('Invalid message format:', message);
        sendResponse({status: 'error', error: 'Invalid message format'});
        return true;
    }

    // Log incoming message
    console.log('Received message:', message);

    switch (message.type) {
        case 'request_sync':
            // Handle sync request from content script
            ServerConnection.debouncedSync()
                .then(() => sendResponse({status: 'success'}))
                .catch(error => sendResponse({status: 'error', error: error.message}));
            break;

        case MessageTypes.HANDLE_APPLY:
            if (!message.data) {
                console.error('Missing data in HANDLE_APPLY message');
                sendResponse({status: 'error', error: 'Missing data'});
                return true;
            }
            handleApplyRequest(message.data.jobId, message.data.applyType)
                .then(sendResponse)
                .catch(error => sendResponse({ error: error.message }));
            break;

        case 'add_to_blacklist':
            if (!message.data?.company) {
                sendResponse({status: 'error', error: 'Missing company name'});
                return true;
            }
            ServerConnection.addToBlacklist(message.data.company, message.data.reason, message.data.notes)
                .then(() => sendResponse({status: 'success'}))
                .catch(error => sendResponse({status: 'error', error: error.message}));
            break;

        case 'remove_from_blacklist':
            if (!message.data?.company) {
                sendResponse({status: 'error', error: 'Missing company name'});
                return true;
            }
            ServerConnection.removeFromBlacklist(message.data.company)
                .then(() => sendResponse({status: 'success'}))
                .catch(error => sendResponse({status: 'error', error: error.message}));
            break;

        case 'preliminary_filter':
            if (!message.data) {
                console.error('Missing data in preliminary_filter message');
                sendResponse({status: 'error', error: 'Missing data'});
                return true;
            }
            ServerConnection.handlePreliminaryFilter(message.data)
                .then(result => sendResponse({data: result}))
                .catch(error => sendResponse({error: error.message}));
            break;

        case 'detailed_filter':
            if (!message.data) {
                console.error('Missing data in detailed_filter message');
                sendResponse({ status: 'error', error: 'Missing data' });
                return true;
            }
            ServerConnection.handleDetailedFilter(message.data)
                .then(result => sendResponse({data: result}))
                .catch(error => sendResponse({error: error.message}));
            break;

        default:
            console.warn('Unknown message type:', message.type);
            sendResponse({status: 'error', error: 'Unknown message type'});
    }
    return true; // Keep the message channel open for async response
});

// Initialize ServerConnection when extension loads
ServerConnection.initialize();
