import {CompanyLocationInfo, GlassdoorRating, JobDetailedInfo, JobInfo, Selectors} from './constants';

export class LinkedInJobParser {
    static getJobIdentifier(jobListing: Element): string | null {
        // Try to get a stable identifier for the job listing
        try {
            // First try to get from href
            const jobLink = jobListing.querySelector('a[href*="currentJobId="]') as HTMLAnchorElement;
            if (jobLink) {
                const match = jobLink.href.match(/currentJobId=(\d+)/);
                if (match) return match[1] ?? null;
            }

            // Try data-occludable-job-id
            const occludableId = jobListing.getAttribute('data-occludable-job-id');
            if (occludableId) return occludableId;

            // Try data-job-id from container
            const jobContainer = jobListing.querySelector('[data-job-id]');
            if (jobContainer) {
                const containerId = jobContainer.getAttribute('data-job-id');
                if (containerId && containerId !== 'search') return containerId;
            }

            // For base job lists before login
            const id = jobListing.querySelector('[data-entity-urn]')
                ?.getAttribute('data-entity-urn')
                ?.split(':')
                .pop();
            if (id) return id;

            // If no valid ID found, create a stable hash from the content
            const titleElement = jobListing.querySelector(Selectors.TITLE);
            const subtitleElement = jobListing.querySelector(Selectors.COMPANY_NAME_DIV) || jobListing.querySelector(Selectors.COMPANY_NAME_OR_JOB_INFO);

            if (titleElement && subtitleElement) {
                const title = titleElement.textContent?.trim() || '';
                const subtitle = subtitleElement.textContent?.trim() || '';
                return `${title}-${subtitle}`.replace(/[^a-zA-Z0-9]/g, '');
            }

            return null;
        } catch (error) {
            console.error('Error getting job identifier:', error);
            return null;
        }
    }

    static parseGlassdoorRating(element: Element | null | undefined): GlassdoorRating {
        const defaultRating: GlassdoorRating = { rating: 0, reviewCount: 0, isValid: false };
        
        if (!element) return defaultRating;
        
        try {
            // First check if it's "Company not found"
            const linkElement = element.querySelector(Selectors.GLASSDOOR_LINK);
            if (linkElement?.textContent?.trim().includes('Company not found')) {
                return defaultRating;
            }
            
            // Find rating span
            const ratingSpan = element.querySelector(Selectors.GLASSDOOR_RATING);
            if (!ratingSpan) return defaultRating;
            
            const ratingText = ratingSpan.textContent?.trim() || '';
            if (ratingText === 'N/A') {
                return defaultRating;
            }
            
            // Parse rating (e.g. "3.7 ★" -> 3.7)
            const rating = parseFloat(ratingText.replace('★', '').trim());
            
            // Find review count and handle both formats
            const reviewSpan = element.querySelector(Selectors.GLASSDOOR_REVIEWS);
            const reviewText = reviewSpan?.textContent?.trim() || '';
            let reviewCount = 0;
            
            if (reviewText) {
                // Remove bullet point and spaces, then extract number part
                const cleanText = reviewText.replace(/^[•\s]+/, '').replace(/\s+Reviews$/, '');
                
                // Handle "k" format (e.g. "1.5k" -> 1500)
                if (cleanText.toLowerCase().includes('k')) {
                    const numStr = cleanText.toLowerCase().replace('k', '');
                    reviewCount = Math.round(parseFloat(numStr) * 1000);
                } else {
                    // Handle regular format (e.g. "145" -> 145)
                    reviewCount = parseInt(cleanText, 10);
                }
            }

            return {
                rating,
                reviewCount,
                isValid: !isNaN(rating) && rating > 0
            };
        } catch (error) {
            console.error('Error parsing Glassdoor rating:', error);
            return defaultRating;
        }
    }

    static async waitForGlassdoorRating(companyElement: Element | null): Promise<GlassdoorRating> {
        if (!companyElement) {
            return { rating: 0, reviewCount: 0, isValid: false };
        }

        return new Promise((resolve) => {
            let timeoutHandle: number;
            let observer: MutationObserver;

            const cleanup = () => {
                clearTimeout(timeoutHandle);
                observer?.disconnect();
            };

            const checkRating = () => {
                const ratingWrapper = companyElement.querySelector(Selectors.GLASSDOOR_LABEL_WRAPPER);
                if (ratingWrapper && this.isRatingPopulated(ratingWrapper)) {
                    cleanup();
                    resolve(this.parseGlassdoorRating(ratingWrapper));
                    return true;
                } else if (!ratingWrapper) {
                    // inDoor is not working or does not exist
                    cleanup();
                    resolve({ rating: 0, reviewCount: 0, isValid: false });
                    return false;
                }
                return false;
            };

            observer = new MutationObserver((mutations) => {
                if (checkRating()) return;
            });

            observer.observe(companyElement, {
                childList: true,
                subtree: true,
                characterData: true,
                attributes: true
            });

            // Set timeout
            timeoutHandle = setTimeout(() => {
                cleanup();
                resolve({ rating: 0, reviewCount: 0, isValid: false });
            }, 3000);

            // Do initial check
            checkRating();
        });
    }

    // Helper method to check if rating is fully populated
    private static isRatingPopulated(ratingWrapper: Element): boolean {
        const ratingElement = ratingWrapper.querySelector(Selectors.GLASSDOOR_RATING);
        const reviewsElement = ratingWrapper.querySelector(Selectors.GLASSDOOR_REVIEWS);
        const loadingElement = ratingWrapper.querySelector('.loading');

        // Check if loading indicator is gone and rating/reviews are populated
        return (
            (!loadingElement || loadingElement.classList.contains('display-none')) &&
            ratingElement?.textContent?.trim() !== '★' && // Default star before population
            reviewsElement?.textContent?.trim() !== '•' // Default bullet before population
        );
    }

    // Helper to get element's DOM path for debugging
    private static getElementPath(element: Element): string {
        const path: string[] = [];
        let current = element;
        
        while (current && current !== document.documentElement) {
            let selector = current.tagName.toLowerCase();
            if (current.id) {
                selector += `#${current.id}`;
            } else if (current.className) {
                selector += `.${current.className.split(' ').join('.')}`;
            }
            path.unshift(selector);
            current = current.parentElement!;
        }
        
        return path.join(' > ');
    }

    static async getBasicJobInfo(jobListing: Element): Promise<JobInfo | null> {
        const jobCard = jobListing.querySelector(Selectors.JOB_CARD);
        if (!jobCard) return null;

        const titleElement = jobCard.querySelector(Selectors.TITLE);
        const companyElement = jobCard.querySelector(Selectors.COMPANY_NAME_OR_JOB_INFO);

        const title = titleElement?.textContent?.trim() || '';
        const {company, location} = this.getNameLocationFromCompanyElement(companyElement);
        
        // Wait for Glassdoor rating
        console.log("Waiting for Glassdoor rating, company: " + company);
        const glassdoorRating = await this.waitForGlassdoorRating(companyElement);
        console.log("Glassdoor rating: " + glassdoorRating.rating);

        const jobId = this.getJobIdentifier(jobListing);
        if (jobId)
            return {
                jobId: jobId,
                title,
                company,
                location,
                glassdoorRating
            };
        else
            return null;
    }

    static getNameLocationFromCompanyElement(companyElement: Element | null): CompanyLocationInfo {
        if (!companyElement) return { company: '', location: '' };

        let company;
        let location;

        // Try the new structure first
        const companyDiv = companyElement.querySelector(Selectors.COMPANY_NAME_DIV);
        const locationDiv = companyElement.querySelector(Selectors.LOCATION_DIV);

        if (companyDiv && locationDiv) {
            // New structure path
            company = companyDiv.textContent?.trim() || '';
            location = locationDiv.textContent?.trim() || '';
        } else {
            // Fallback to the original method for backward compatibility
            const locationSpan = companyElement.querySelector(Selectors.COMPANY_LOCATION_SPAN);
            const fullCompanyText = locationSpan?.textContent?.trim() || '';

            // Split company and location by the middle dot (LinkedIn specific format)
            const lastDotIndex = fullCompanyText.lastIndexOf('·');
            company = lastDotIndex === -1 ? fullCompanyText : fullCompanyText.slice(0, lastDotIndex).trim();
            location = lastDotIndex === -1 ? '' : fullCompanyText.slice(lastDotIndex + 1).trim();
        }

        // Process location text (same for both code paths)
        location = location.replace(/\s*\((Hybrid|On-site|Remote)\)\s*$/, '').trim();

        return { company, location };
    }

    static async getDetailedJobInfo(jobCard: Element): Promise<JobDetailedInfo | null> {
        try {
            // Wait for job details to load
            await this.waitForJobDetails();
            
            const jobId = this.getJobIdentifier(jobCard.parentElement!);
            const title = document.querySelector(Selectors.TITLE_DETAILED)?.textContent?.trim() || '';
            const company = document.querySelector(Selectors.COMPANY_NAME_DETAILED)?.textContent?.trim() || '';
            const description = (document.querySelector(Selectors.DESCRIPTION_DETAILED) as HTMLElement)?.innerText.trim() || '';
            
            // Get location from the first low-emphasis text in the primary description container
            const location = document.querySelector(Selectors.LOCATION_DETAILED)?.textContent?.trim() || '';

            // Get the full text from the company description paragraph
            const aboutCompanyText = document.querySelector('.jobs-company__company-description');
            const aboutCompany = aboutCompanyText?.textContent?.trim() || '';
            
            // Get company size from the first inline information element
            const companySizeElement = document.querySelector('.jobs-company__inline-information');
            const companySize = companySizeElement?.textContent?.trim() || '';
            
            // Wait for Glassdoor rating in detailed view
            const companyContainer = document.querySelector(Selectors.JOB_DETAILED_TOP_CARD_CONTAINER);
            const glassdoorRating = await this.waitForGlassdoorRating(companyContainer);
            
            if (!jobId || !title || !description) {
                console.error('Missing required job details');
                return null;
            }

            return {
                jobId: jobId,
                title,
                company,
                location,
                description,
                aboutCompany,
                companySize,
                glassdoorRating
            };
        } catch (error) {
            console.error('Error getting detailed job info:', error);
            return null;
        }
    }

    private static async waitForJobDetails(): Promise<void> {
        const maxAttempts = 10;
        const delay = 200;
        let attempts = 0;

        while (attempts < maxAttempts) {
            const jobTitle = document.querySelector('.job-details-jobs-unified-top-card__job-title');
            const jobDescription = document.querySelector('.jobs-description__content');
            const companyNameContainer = document.querySelector('.job-details-jobs-unified-top-card__company-name');
            
            // Wait for the basic elements to load
            if (!jobTitle || !jobDescription || !companyNameContainer) {
                await new Promise(resolve => setTimeout(resolve, delay));
                attempts++;
                continue;
            }

            // Check if company name is a link (indicating presence of about section)
            const companyNameLink = companyNameContainer.querySelector('a');
            
            // If company name is not a link, we don't need to wait for about section
            if (!companyNameLink) {
                return;
            }

            // If company name is a link, wait for about section to load
            const aboutCompanyText = document.querySelector('.jobs-company__company-description');
            if (aboutCompanyText) {
                return;
            }

            await new Promise(resolve => setTimeout(resolve, delay));
            attempts++;
        }
    }
} 