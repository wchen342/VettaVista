import logging
from typing import List, Tuple
import re

from vettavista_backend.config import resume, search
from vettavista_backend.config.global_constants import JobStatus, HIGH_THRESHOLD, LOW_THRESHOLD
from vettavista_backend.modules.business.cache.job_cache_service import JobCacheService
from vettavista_backend.modules.models.services import JobInfo, JobStatusResponse, FilterType
from vettavista_backend.modules.business.filter.base_filter_service import BaseFilterService
from vettavista_backend.modules.utils import block_base_methods
from vettavista_backend.modules.business.utils.language_detector import HybridLanguageDetector
from vettavista_backend.modules.business.utils.title_matcher import AdvancedEmbeddingMatcher
from vettavista_backend.modules.storage import BlacklistStorage, JobHistoryStorage

logger = logging.getLogger(__name__)

@block_base_methods(allowed_methods=["clear_cache"])
class PreliminaryFilterService(BaseFilterService):
    def __init__(
            self,
            blacklist_storage: BlacklistStorage,
            job_history_storage: JobHistoryStorage,
            job_cache: JobCacheService,
            title_matcher: AdvancedEmbeddingMatcher
    ):
        """Initialize the preliminary filter service."""
        super().__init__(
            blacklist_storage=blacklist_storage,
            job_history_storage=job_history_storage,
            job_cache=job_cache)
        self.title_matcher = title_matcher
        self.bad_words = search.bad_words
        # Create regex pattern for bad words with word boundaries
        self.bad_words_pattern = re.compile(r'\b(' + '|'.join(map(re.escape, self.bad_words)) + r')\b', 
                                          flags=re.IGNORECASE)
        self.language_detector = HybridLanguageDetector()
        self.lang_detect_remove_pattern = re.compile('|'.join(map(re.escape, search.lang_detect_remove_words)),
                                                     flags=re.IGNORECASE)
        
    async def should_skip_preliminary(self, job: JobInfo) -> Tuple[bool, str]:
        """Preliminary filtering with language detection and bad words"""
        company = job.company
        job_id = job.jobId
        title = job.title.lower() if job.title else ""
        
        logger.info(f"\n=== Preliminary Filter for: {title} ===")
        logger.info(f"Company: {company}")
        logger.info(f"Job ID: {job_id}")
        
        # Check bad words in title using regex pattern
        if self.bad_words_pattern.search(title):
            matched_word = self.bad_words_pattern.search(title).group()
            logger.info(f"Found bad word in title: {matched_word}")
            return True, f"Title contains excluded word: {matched_word}"
        
        # Company blacklist check
        if await self.blacklist_storage.is_blacklisted(company):
            logger.info(f"Company is blacklisted")
            return True, f"Company {company} is blacklisted"
            
        # Previously rejected check
        if await self.job_history_storage.is_rejected(job_id):
            logger.info(f"Job was previously rejected")
            return True, f"Job {job_id} was previously rejected"
        
        # Language check with improved detection
        if title:
            detected_lang, confidence = self.language_detector.detect_language(
                self.lang_detect_remove_pattern.sub('', title))
            if detected_lang and confidence > 0.25:  # Only act if confident
                logger.info(f"Final language detection: {detected_lang} (confidence: {confidence:.3f})")
                if detected_lang not in [lang for lang in resume.skills['languages']]:
                    logger.info(f"Language {detected_lang} not in accepted languages: {resume.skills['languages']}")
                    return True, f"Job posting language ({detected_lang}) not in user's languages"
            else:
                logger.info(f"Language detection confidence too low ({confidence:.3f}), skipping language check")
        
        # Check Glassdoor rating if valid
        if job.glassdoorRating.isValid:
            if job.glassdoorRating.rating < 3.5:  # Very low rating
                logger.info(f"Company has very low Glassdoor rating: {job.glassdoorRating.rating}")
                return True, f"Company has poor rating ({job.glassdoorRating.rating}★)"
            elif job.glassdoorRating.rating < 3.9 and job.glassdoorRating.reviewCount >= 15:
                # Only consider low ratings if there are enough reviews
                logger.info(f"Company has low Glassdoor rating with sufficient reviews: {job.glassdoorRating.rating}★ ({job.glassdoorRating.reviewCount} reviews)")
                return True, f"Company has low rating ({job.glassdoorRating.rating}★) with {job.glassdoorRating.reviewCount} reviews"
            else:
                logger.info(f"Company has normal Glassdoor rating: {job.glassdoorRating.rating}")
        
        logger.info("Preliminary filter passed")
        return False, ""

    def get_preliminary_status(self, job_data: JobInfo) -> JobStatusResponse:
        """Get preliminary match status for a job"""
        title = job_data.title
        logger.info(f"\n=== Getting Preliminary Status for: {title} ===")

        # Get title match score
        title_score = self.title_matcher.match_title(title)
        logger.info(f"Title score: {title_score:.3f}")
        logger.info(f"Thresholds - High: {HIGH_THRESHOLD}, Low: {LOW_THRESHOLD}")

        # Determine status based on title match
        if title_score > HIGH_THRESHOLD:
            status = JobStatusResponse(status=JobStatus.LIKELY_MATCH, reasons=["Title matches well"],
                                       title_score=title_score)
        elif title_score > LOW_THRESHOLD:
            status = JobStatusResponse(status=JobStatus.POSSIBLE_MATCH, reasons=["Title somewhat matches"],
                                       title_score=title_score)
        else:
            status = JobStatusResponse(status=JobStatus.NOT_LIKELY, reasons=["Title does not match well"],
                                       title_score=title_score)

        logger.info(f"Final status: {status}")
        return status
        
    async def preliminary_filter(self, jobs: List[JobInfo]) -> List[JobStatusResponse]:
        """Quick filtering based on job title and location"""
        logger.info(f"\n=== Preliminary Filter Request ===")
        logger.info(f"Number of jobs to filter: {len(jobs)}")
        
        results = []
        for job in jobs:
            logger.info(f"Processing job:")
            logger.info(f"Job ID: {job.jobId}")
            logger.info(f"Title: {job.title}")
            logger.info(f"Company: {job.company}")
            logger.info(f"Location: {job.location}")
            logger.info(f"Raw job data: {job}")

            if not all(hasattr(job, k) for k in ['title', 'company', 'location', 'jobId']):
                missing_fields = [k for k in ['title', 'company', 'location', 'jobId'] if not hasattr(job, k)]
                error_msg = f"Missing required fields: {missing_fields}"
                logger.error(error_msg)
                raise ValueError(error_msg)
                
            # Check if we have cached preliminary results
            cached = await self.get_cached_result(job.jobId)
            if cached and cached.filter_type == FilterType.PRELIMINARY:
                logger.info(f"Found cached preliminary result with status: {cached.status}")
                logger.info(f"Cached reasons: {cached.reasons}")
                results.append(cached)
                continue
                
            # Check if we should skip first (cheaper operation)
            should_skip, reason = await self.should_skip_preliminary(job)
            if should_skip:
                # Determine status based on reason
                status = JobStatus.CONFIRMED_NO_MATCH if (
                        "Job posting language" in reason or
                        "poor rating" in reason or
                        "excluded word" in reason) else JobStatus.NOT_LIKELY
                result = JobStatusResponse(
                    status=status,
                    reasons=[reason],
                    filter_type=FilterType.PRELIMINARY
                )
                results.append(result)
                continue
                
            # Only do title matching if we haven't skipped
            result = self.get_preliminary_status(job)
            result.filter_type = FilterType.PRELIMINARY  # Set filter type
            await self.cache_filter_result(job.jobId, result)
            results.append(result)
            
        return results