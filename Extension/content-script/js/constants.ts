// Constants
export const CACHE_EXPIRY_MS: number = 7 * 24 * 60 * 60 * 1000; // 7 days

// Job processing states
export enum JobState {
    INITIAL = 'initial',
    FILTERING = 'filtering',
    BLACKLISTED = 'blacklisted',
    HISTORY = 'history',
    COMPLETE = 'complete',
    ERROR = 'error'
}

// Job status (both internal state and visual representation)
export enum JobStatus {
    UNKNOWN = 'unknown',
    LIKELY_MATCH = 'likely_match',
    POSSIBLE_MATCH = 'possible_match',
    NOT_LIKELY = 'not_likely',
    CONFIRMED_MATCH = 'confirmed_match',
    CONFIRMED_NO_MATCH = 'confirmed_no_match',
    ERROR = 'error'
}

// Application Status
export enum ApplicationStatus {
    NEW = 'new',
    REVIEWING = 'reviewing',
    WILL_APPLY = 'will_apply',
    APPLIED = 'applied',
    REJECTED = 'rejected',
    IN_PROGRESS = 'in_progress',
    OFFER = 'offer',
    ACCEPTED = 'accepted',
    DECLINED = 'declined',
    NOT_INTERESTED = 'not_interested',
    NO_RESPONSE = 'no_response',
}

// Blacklist Status for CSS
export enum BlacklistStatus {
    BLACKLISTED = 'blacklisted'
}


export type jobIdType = string;

// Filter result interface used across multiple files
export interface FilterResultBase {
    status: JobStatus;
    reasons?: string[];
}

export type PreliminaryFilterResult = FilterResultBase;

export interface DetailedFilterResult extends FilterResultBase {
    match: boolean;
}

export type FilterResult = PreliminaryFilterResult | DetailedFilterResult;

export type CachedFilterResult = {
    result: FilterResult,
    timestamp: string
}

export interface BlacklistEntry {
    company: string;
    reason: string;
    notes?: string;
    timestamp: string;
}

export interface JobHistoryEntry {
    job_id: jobIdType;
    title: string;
    company: string;
    location: string;
    url: string;
    match_status: JobStatus;
    application_status: ApplicationStatus;
    rejection_reason: string;
    skip_reason: string;
    user_notes: string;
    date_created: string;
    date_updated: string;
    date_applied: string;
    date_rejected: string;
    resume_path: string;
    cover_letter_path: string;
}

export interface JobStateData {
    state: JobState;
    company?: string;
    tooltip?: string;
    jobInfo?: JobInfo;
    filterResult: FilterResult;
    timestamp: string;
}

export interface ServerData {
    filterResults?: Record<string, FilterResult>;
    blacklist?: Array<{ company: string } & BlacklistEntry>;
    history?: Array<JobHistoryEntry>;
}

// Batch processing configuration
export interface BatchConfigType {
    maxRetries: number;
    retryDelay: number;
    batchSize: number;
    batchDelay: number;
    processingTimeout: number;
    observerDebounce: number;
}

export const BatchConfig: BatchConfigType = {
    maxRetries: 3,
    retryDelay: 2000,
    batchSize: 6,
    batchDelay: 1000,
    processingTimeout: 45000,
    observerDebounce: 500
} as const;

export interface GlassdoorRating {
    rating: number;
    reviewCount: number;
    isValid: boolean;
}

export interface JobInfo {
    jobId: jobIdType;
    title: string;
    company: string;
    location: string;
    glassdoorRating: GlassdoorRating;
}

export interface JobDetailedInfo extends JobInfo {
    description: string;
    aboutCompany: string;
    companySize: string;
}

export interface CompanyLocationInfo {
    company: string;
    location: string;
}

// Type definitions
export interface Selectors {
    JOB_CARD: string;
    JOB_LIST_ITEM: string;
    JOB_CONTAINER: string;
    COMPANY_NAME_OR_JOB_INFO: string;
    TITLE: string;
    BLACKLIST_BUTTON: string;
    APPLY_BUTTON: string;
    COMPANY_LOCATION_SPAN: string;
    COMPANY_NAME_DIV: string;
    LOCATION_DIV: string;
    JOB_DETAILED_TOP_CARD_CONTAINER: string;
    GLASSDOOR_LABEL: string;
    GLASSDOOR_RATING: string;
    GLASSDOOR_REVIEWS: string;
    GLASSDOOR_LINK: string;
    GLASSDOOR_LABEL_WRAPPER: string;
    TITLE_DETAILED: string;
    COMPANY_NAME_DETAILED: string;
    DESCRIPTION_DETAILED: string;
    LOCATION_DETAILED: string;
}

// Selectors for job elements
export const Selectors: Selectors = {
    JOB_CARD: '.job-card-container, .job-search-card, .job-card-job-posting-card-wrapper, [data-job-id]',
    JOB_LIST_ITEM: 'li.occludable-update[data-occludable-job-id], li.scaffold-layout__list-item[data-occludable-job-id], li:has([data-job-id]), li:has(div[data-entity-urn])',
    JOB_CONTAINER: '.scaffold-layout__list, .jobs-search-results-list, .jobs-search__job-details, .scaffold-finite-scroll__content',
    COMPANY_NAME_OR_JOB_INFO: '.job-card-container__primary-description, .job-card-container__company-name, .base-search-card__subtitle, .artdeco-entity-lockup',
    TITLE: '.job-card-list__title--link strong, .job-card-container__link strong, .base-search-card__title, .artdeco-entity-lockup__title strong',
    BLACKLIST_BUTTON: '.blacklist-btn',
    APPLY_BUTTON: 'button.jobs-apply-button[data-job-id], button.jobs-apply-button[role="link"]',
    COMPANY_LOCATION_SPAN: '.artdeco-entity-lockup__subtitle span[dir="ltr"]',
    COMPANY_NAME_DIV: '.artdeco-entity-lockup__subtitle [dir="ltr"]',
    LOCATION_DIV: '.artdeco-entity-lockup__caption [dir="ltr"]',
    JOB_DETAILED_TOP_CARD_CONTAINER: '.job-details-jobs-unified-top-card__container--two-pane',
    GLASSDOOR_LABEL: '.glassdoor-label',
    GLASSDOOR_RATING: '.glassdoor-rating',
    GLASSDOOR_REVIEWS: '.glassdoor-reviews',
    GLASSDOOR_LINK: '#glassdoor-link',
    GLASSDOOR_LABEL_WRAPPER: '.glassdoor-label-wrapper',
    TITLE_DETAILED: '.job-details-jobs-unified-top-card__job-title, .top-card-layout__title',
    COMPANY_NAME_DETAILED: '.job-details-jobs-unified-top-card__company-name, .topcard__org-name-link',
    DESCRIPTION_DETAILED: '.jobs-description__content, .show-more-less-html__markup',
    LOCATION_DETAILED: '.job-details-jobs-unified-top-card__primary-description-container .tvm__text--low-emphasis, .topcard__flavor--bullet:not(.num-applicants__caption)',
} as const;

// Observer configuration
export const ObserverConfig: MutationObserverInit = {
    attributes: true,
    childList: true,
    subtree: true,
    attributeOldValue: true
} as const;

export function validateDetailedFilterResponse(response: unknown): response is DetailedFilterResult {
    if (!response || typeof response !== 'object') return false;

    return 'match' in response &&
        'reasons' in response &&
        'status' in response &&
        Array.isArray((response as DetailedFilterResult).reasons)
}

export function zip<T, U>(a: T[], b: U[]): [T, U][] {
    if (!Array.isArray(a) || !Array.isArray(b)) {
        throw new Error('zip: Both arguments must be arrays');
    }
    if (a.length !== b.length) {
        throw new Error(`zip: Arrays must have same length (${a.length} !== ${b.length})`);
    }
    return a.map((k, i) => [k, b[i]!]);
}

export const MessageTypes = {
    HANDLE_APPLY: 'HANDLE_APPLY',
    GET_APPLY_STATUS: 'GET_APPLY_STATUS'
} as const;