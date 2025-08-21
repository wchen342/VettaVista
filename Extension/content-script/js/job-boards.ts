import {ApplicationStatus, BlacklistStatus, jobIdType, JobStatus, Selectors} from './constants';
import {logDebug} from "./debug";

export interface JobBoard {
    hostname: string;
    id: string;
    attributes: Array<{
        name: string;
    }>;
    getJobListings(): HTMLElement[];
    findJobListingById(jobId: string): HTMLElement | null;
    updateJobCardStatus(jobListing: Element, status: JobStatus): void;
    updateJobCardBlacklistStatus(jobListing: Element, isBlacklisted: boolean): void;
    updateJobCardApplicationStatus(jobListing: Element, application_status: ApplicationStatus): void;
    setJobCardTooltip(jobListing: Element, tooltip: string): void;
}

export class LinkedInJobBoard implements JobBoard {
    hostname = "linkedin.com";
    id = "linkedIn";
    attributes = [
        {
            name: "companyName",
        }
    ];

    getJobListings(): HTMLElement[] {
        const elements = Array.from(document.querySelectorAll(Selectors.JOB_LIST_ITEM))
            .filter((el): el is HTMLElement => el instanceof HTMLElement);
        return elements;
    }

    findJobListingById(jobId: jobIdType): HTMLElement | null {
        // First try direct match
        const element = document.querySelector(`[data-job-id="${jobId}"], [data-occludable-job-id="${jobId}"], [data-entity-urn="urn:li:jobPosting:${jobId}"]`);
        if (element) {
            // For new layout, get the li parent
            const liElement = element.closest('li') || element;
            return liElement as HTMLElement;
        }

        // Try to find element by currentJobId in href
        const jobLink = document.querySelector(`a[href*="currentJobId=${jobId}"]`);
        if (jobLink) {
            // Walk up to find the li element containing the job card
            return jobLink.closest('li.discovery-templates-entity-item');
        }

        return null;
    }

    updateJobCardStatus(jobListing: Element, status: JobStatus): void {
        const jobCard = jobListing.querySelector(Selectors.JOB_CARD);
        if (!jobCard) return;

        logDebug('Updating job card status:', { status, jobCard });
        (jobCard as HTMLElement).dataset.status = status;
    }

    updateJobCardBlacklistStatus(jobListing: Element, isBlacklisted: boolean): void {
        const jobCard = jobListing.querySelector(Selectors.JOB_CARD) as HTMLElement;
        if (!jobCard) return;

        logDebug('Updating job card blacklist status:', { isBlacklisted, jobCard });
        if (isBlacklisted &&
            (!jobCard.dataset.blacklistStatus || jobCard.dataset.blacklistStatus !== BlacklistStatus.BLACKLISTED)) {
            jobCard.dataset.blacklistStatus = BlacklistStatus.BLACKLISTED;
        } else if (!isBlacklisted && jobCard.dataset.blacklistStatus &&
            jobCard.dataset.blacklistStatus === BlacklistStatus.BLACKLISTED) {
            delete jobCard.dataset.blacklistStatus;
        }
    }

    updateJobCardApplicationStatus(jobListing: Element, application_status: ApplicationStatus): void {
        const jobCard = jobListing.querySelector(Selectors.JOB_CARD);
        if (!jobCard) return;

        logDebug('Updating job card application status:', { application_status, jobCard });
        (jobCard as HTMLElement).dataset.applicationStatus = application_status;
    }

    setJobCardTooltip(jobListing: Element, tooltip: string): void {
        const jobCard = jobListing.querySelector(Selectors.JOB_CARD);
        if (!jobCard) return;

        logDebug('Setting job card tooltip:', { tooltip, jobCard });
        if (tooltip) {
            (jobCard as HTMLElement).dataset.tooltip = tooltip;
        } else {
            delete (jobCard as HTMLElement).dataset.tooltip;
        }
    }
}

export class JobBoards {
    static #jobBoards: JobBoard[] = [
        new LinkedInJobBoard()
    ];

    static getJobBoardByHostname(hostname: string = location.hostname): JobBoard | undefined {
        return this.#jobBoards.find(
            (jobBoard) =>
                hostname.endsWith(`.${jobBoard.hostname}`) ||
                hostname === jobBoard.hostname
        );
    }
} 