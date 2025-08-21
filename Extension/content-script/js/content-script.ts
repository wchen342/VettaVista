import {JobStateManager} from './job-state-manager';
import {SyncManager} from './sync-manager';
import {JobUIManager} from './job-ui-manager';
import {JobFilterService} from './job-filter-service';
import {JobListingManager} from './job-listing-manager';
import {logMutation, setupAttributeDebugWrappers} from './debug';
import {JobBoards} from './job-boards';
import {JobHistoryManager} from "./job-history-manager";
import {BlacklistManager} from "./blacklist-manager";
import {ObserverConfig} from "./constants";
import {JobApplicationManager} from './job-application-manager';
import {CacheService} from "./cache-service";

(async () => {
    // Set up attribute change monitoring immediately
    const attributeObserver = new MutationObserver((mutations: MutationRecord[]) => {
        mutations.forEach(logMutation);
    });

    // Start observing immediately
    attributeObserver.observe(document.documentElement, ObserverConfig);

    // Set up debug wrappers
    setupAttributeDebugWrappers();

    // Initialize
    const jobBoard = JobBoards.getJobBoardByHostname(location.hostname);
    if (!jobBoard) return;

    const cacheService = new CacheService();
    const syncManager = new SyncManager();
    const filterService = new JobFilterService();
    const historyManager = new JobHistoryManager();
    const blacklistManager = new BlacklistManager();
    const stateManager = new JobStateManager(filterService, blacklistManager, historyManager);
    const uiManager = new JobUIManager(jobBoard, stateManager, historyManager);
    const applicationManager = new JobApplicationManager();

    const jobListingManager = await JobListingManager.create(
        jobBoard,
        cacheService,
        blacklistManager,
        historyManager,
        filterService,
        stateManager,
        uiManager,
        applicationManager,
    );
    await syncManager.startSync();

    // Add message listener for popup
    chrome.runtime.onMessage.addListener((
        message: { type: string },
        sender,
        sendResponse
    ) => {
        if (message.type === 'check_job_board') {
            const jobBoard = JobBoards.getJobBoardByHostname(location.hostname);
            sendResponse({ isJobBoard: !!jobBoard });
            return true;  // Keep message channel open for async response
        }
        return false;  // For unhandled messages
    });

    // // Listen for messages from popup
    // chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    //   switch (request.action) {
    //       case 'blacklistCompany':
    //           blacklistManager.addCompany(request.company, request.reason);
    //           break;
    //       case 'removeFromBlacklist':
    //           blacklistManager.removeCompany(request.company);
    //           break;
    //       case 'updateJobApplication':
    //           jobListingManager.updateJobApplication(request.jobData);
    //           break;
    //       // ... other message handlers ...
    //   }
    //   return true;
    // });
})(); 