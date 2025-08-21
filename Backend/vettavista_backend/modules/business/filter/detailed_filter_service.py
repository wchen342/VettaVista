import logging
import re
import traceback
from datetime import datetime
from typing import Tuple, Dict, Optional

import numpy as np

from vettavista_backend.config import resume, search
from vettavista_backend.config.global_constants import JobStatus, HIGH_THRESHOLD, LOW_THRESHOLD
from vettavista_backend.modules.ai import ClaudeServiceProtocol, ClaudeService
from vettavista_backend.modules.business.cache.job_cache_service import JobCacheService
from vettavista_backend.modules.business.filter.base_filter_service import BaseFilterService
from vettavista_backend.modules.business.utils.language_detector import HybridLanguageDetector
from vettavista_backend.modules.business.utils.skill_matcher import SimpleSkillMatcher
from vettavista_backend.modules.business.utils.title_matcher import AdvancedEmbeddingMatcher
from vettavista_backend.modules.models.services import JobDetailedInfo, JobStatusResponse, JobAnalysisInfo, FilterType, \
    VisaSupport
from vettavista_backend.modules.storage import BlacklistStorage, JobHistoryStorage
from vettavista_backend.modules.utils import block_base_methods, parse_employee_count

logger = logging.getLogger(__name__)


@block_base_methods(allowed_methods=["clear_cache"])
class DetailedFilterService(BaseFilterService):
    def __init__(
        self,
        blacklist_storage: BlacklistStorage,
        job_history_storage: JobHistoryStorage,
        title_matcher: AdvancedEmbeddingMatcher,
        skill_matcher: SimpleSkillMatcher,
        job_cache: JobCacheService,
        claude_service: Optional[ClaudeServiceProtocol] = None,
    ):
        """Initialize the detailed filter service."""
        super().__init__(
            blacklist_storage=blacklist_storage,
            job_history_storage=job_history_storage,
            job_cache=job_cache
        )
        self.title_matcher = title_matcher
        self.skill_matcher = skill_matcher
        self.bad_words = search.bad_words
        self.language_detector = HybridLanguageDetector()
        self._claude = claude_service or ClaudeService()

        # Enhanced regex pattern for experience extraction
        self.re_experience = r'(?:(?:minimum|min\.?|at least|>\s*)\s*)?(\d+(?:\.\d+)?)\s*(?:\+|\s*-\s*\d+)?\s*(?:years?|yrs?|y(?:ea)?rs?\.?\s+(?:of\s+)?exp(?:erience)?|months?|mo\.?)'

        # Pre-compute embeddings for experience titles
        self._experience_embeddings = {}
        for exp in resume.experience:
            self._experience_embeddings[exp.title] = self.title_matcher.encode([exp.title])[0]

    def _get_relevant_experience_duration(self, job_title: str, similarity_threshold: float = 0.85) -> float:
        """Calculate total years of relevant experience based on title similarity."""
        total_years = 0.0

        # Get job title embedding using the cached encoder
        job_emb = self.title_matcher.encode(job_title)

        for exp in resume.experience:
            # Get pre-computed experience title embedding if possible
            exp_emb = self._experience_embeddings.get(exp.title, None)
            if exp_emb is None:
                self._experience_embeddings[exp.title] = self.title_matcher.encode([exp.title])[0]
            exp_emb = self._experience_embeddings[exp.title]

            # Calculate similarity
            similarity = float(np.dot(job_emb, exp_emb) / (
                np.linalg.norm(job_emb) * np.linalg.norm(exp_emb)
            ))

            # Only count experience if titles are similar enough
            if similarity >= similarity_threshold:
                if exp.end == datetime.max:
                    end = datetime.now()
                else:
                    end = exp.end
                
                # Calculate duration in years
                duration = (end - exp.start).days / 365.25
                total_years += duration
                logger.info(f"Including experience: {exp.title} (similarity: {similarity:.2f}, duration: {duration:.1f} years)")
            else:
                logger.info(f"Skipping experience: {exp.title} (similarity: {similarity:.2f} below threshold)")

        return round(total_years, 1)  # Round to 1 decimal place

    def detect_post_language(self, job_description: str) -> str:
        # Detect the language of the job post itself
        post_lang, confidence = self.language_detector.detect_language(job_description)
        if not post_lang:
            post_lang = 'ENGLISH'  # Default to English if detection fails
            logger.warning("Failed to detect job post language, defaulting to English")
        else:
            logger.info(f"Job post language detected: {post_lang} (confidence: {confidence:.2f})")
        return post_lang

    async def extract_years_of_experience(self, job_description: str, exp_dict: Dict) -> float:
        """Extract years of experience required from job description using both regex and Claude"""
        regex_exp = None
        # Try regex first
        try:
            matches = re.finditer(self.re_experience, job_description, re.IGNORECASE)
            experiences = []
            
            for match in matches:
                try:
                    value = float(match.group(1))
                    if 'month' in match.group().lower():
                        value = value / 12
                    experiences.append(value)
                except (ValueError, IndexError):
                    continue

            if experiences:
                regex_exp = min(experiences)  # Take minimum from regex matches
        except Exception as e:
            logger.error(f"Regex experience extraction failed: {e}")

        # Process extract from Claude
        claude_exp = 0
        try:
            if exp_dict["years"] >= 0:
                claude_exp = float(exp_dict["years"]) + (
                    float(exp_dict["months"]) / 12 if exp_dict["months"] >= 0 else 0)
        except Exception as e:
            logger.error(f"Claude experience extraction failed: {e}")

        # Decision logic
        if claude_exp is not None and regex_exp is not None:
            # If both extractors found something, check for significant disagreement
            if abs(claude_exp - regex_exp) > 1:  # More than 1 year difference
                logger.warning(f"Experience requirement extractors disagree: Claude={claude_exp:.1f}, Regex={regex_exp:.1f}. Using Claude's value.")
            return claude_exp  # Prefer Regex's interpretation
        elif claude_exp is not None:
            return claude_exp
        elif regex_exp is not None:
            logger.info("Using regex fallback for experience extraction")
            return regex_exp
        
        return 0  # No experience requirement found

    async def should_skip_job(self, job: JobDetailedInfo) -> Tuple[bool, str, str | None]:
        """Check if job should be skipped based on filters"""
        if not job.description:
            return True, "Error getting job description", None

        # Check company size
        min_employees, max_employees = parse_employee_count(job.companySize)

        # TODO: location handler
        # if (job.location.split(', ')[-1] != ''
        #         and min_employees > 0 and max_employees <= 20):
        #     return True, f"Company too small ({job.companySize})", None

        # Check if company is blacklisted
        if await self.blacklist_storage.is_blacklisted(job.company):
            return True, f"Company {job.company} is blacklisted", None

        # Check if job was previously rejected
        if await self.job_history_storage.is_rejected(job.jobId):
            return True, f"Job {job.jobId} was previously rejected", None

        # Use local language detection for fast filtering
        # Job description is usually long enough for detection to be accurate
        post_lang = self.detect_post_language(job.description)
        resume_languages = set(lang.upper() for lang in resume.skills['languages'])
        required_languages = {post_lang.upper()}
        missing_languages = required_languages - resume_languages

        if missing_languages:
            logger.info(f"\nMissing job post language: {', '.join(missing_languages)}")
            return True, f"Missing job post language", post_lang

        return False, "", post_lang

    async def skip_for_experience_length(self, job: JobDetailedInfo, exp_dict: Dict, margin=1) -> Tuple[bool, str]:
        # Check experience requirements using relevant experience only
        current_experience = self._get_relevant_experience_duration(job.title)
        try:
            required_exp = await self.extract_years_of_experience(job.description, exp_dict)
            if required_exp > 0:  # Only check if we found a requirement
                masters_bonus = 2 if resume.did_masters and 'master' in job.description.lower() else 0
                if required_exp > current_experience + masters_bonus + margin:
                    return True, f"Required experience ({required_exp:.1f} years) exceeds relevant experience ({current_experience:.1f} + {margin:.1f} years)"
        except Exception as e:
            err_message = f"Error extracting experience requirement: {e}"
            logger.error(err_message)
            # Don't skip the job if we can't parse the requirement
            return False, err_message

        return False, f"Relevant experience ({current_experience:.1f} years) exceeds required experience ({required_exp:.1f} years)"

    def _check_visa_and_red_flags(self, visa_support: VisaSupport, red_flags_dict: Dict) -> Tuple[JobStatus | None, str]:
        """Check visa support status and red flags score to determine job status.
        
        Args:
            visa_support: VisaSupport enum value
            red_flags_dict: Dictionary containing red flags score and reasons
            
        Returns:
            Tuple[Optional[JobStatus], str]: (job_status, reason)
            If job_status is None, continue with normal processing
        """
        # First check visa support - immediate rejection if unsupported
        if visa_support == VisaSupport.UNSUPPORTED:
            return JobStatus.CONFIRMED_NO_MATCH, "Job does not provide visa support"
        
        # Get red flags score
        score = red_flags_dict.get("score", 0)
        reasons = red_flags_dict.get("reasons", [])
        
        # High risk checks - Confirmed no match
        if score >= 75:
            reason = "High risk: " + "; ".join(reasons[:3])
            return JobStatus.CONFIRMED_NO_MATCH, reason
        
        # Medium-high risk - Not likely
        if score >= 65:
            reason = "Medium-high risk: " + "; ".join(reasons[:2])
            return JobStatus.NOT_LIKELY, reason

        return None, ""

    async def detailed_filter(self, job: JobDetailedInfo) -> JobStatusResponse:
        """Detailed filtering using Claude for skill analysis"""
        # Cache the job info
        await self._job_cache.set_job_info(job.jobId, job)
        
        # Try get from cache
        result = await self.get_cached_result(job.jobId)
        if result is not None and result.filter_type == FilterType.DETAILED:
            return result

        # First do preliminary check
        should_skip, reason, post_lang = await self.should_skip_job(job)
        if should_skip or post_lang is None:
            logger.info(f"Skipping detailed analysis: {reason}")
            result = JobStatusResponse(
                status=JobStatus.CONFIRMED_NO_MATCH,
                match=False,
                reasons=[reason],
                filter_type=FilterType.DETAILED
            )
            await self.cache_filter_result(job.jobId, result)
            return result

        # Get title match score first
        title_score = self.title_matcher.match_title(job.title)

        # Extract skills and experience together using Claude
        try:
            cached_analysis = await self._job_cache.get_job_analysis(job.jobId)
            if cached_analysis:
                logger.info(f"Using cached analysis for job {job.jobId}")
                skills_dict = cached_analysis.skills_dict
                exp_dict = cached_analysis.experience_dict
                red_flags_dict = cached_analysis.red_flags_dict
                visa_support = cached_analysis.visa_support
            else:
                # Extract skills and experience using Claude if not cached
                logger.info(f"No cached analysis found for job {job.jobId}, performing new analysis")
                skills_dict, exp_dict, red_flags_dict, visa_support = await self._claude.batch_extract_job_info(job.description, post_lang)
                # Cache the results
                analysis_info = JobAnalysisInfo(
                    skills_dict=skills_dict,
                    experience_dict=exp_dict,
                    red_flags_dict=red_flags_dict,
                    visa_support=visa_support,
                    post_language=post_lang
                )
                await self._job_cache.set_job_analysis(job.jobId, analysis_info)

            # Check visa support and red flags
            status, reason = self._check_visa_and_red_flags(visa_support, red_flags_dict)
            if status is not None:
                result = JobStatusResponse(
                    status=status,
                    match=False,
                    reasons=[reason],
                    title_score=title_score,
                    filter_type=FilterType.DETAILED
                )
                await self.cache_filter_result(job.jobId, result)
                return result

            # Check experience requirements
            should_skip, reason = await self.skip_for_experience_length(job, exp_dict)
            if should_skip:
                result = JobStatusResponse(
                    status=JobStatus.CONFIRMED_NO_MATCH,
                    match=False,
                    reasons=[reason],
                    title_score=title_score,
                    filter_type=FilterType.DETAILED
                )
                await self.cache_filter_result(job.jobId, result)
                return result

            # Evaluate match
            is_match, reasons = self.skill_matcher.evaluate_skills_match(skills_dict)

            # Determine final status based on both title and skills
            if is_match and title_score > HIGH_THRESHOLD:
                status = JobStatus.CONFIRMED_MATCH
            elif is_match and title_score > LOW_THRESHOLD:
                status = JobStatus.POSSIBLE_MATCH
            else:
                status = JobStatus.CONFIRMED_NO_MATCH

            result = JobStatusResponse(
                status=status,
                match=is_match,
                reasons=reasons,
                title_score=title_score,
                filter_type=FilterType.DETAILED
            )
            await self.cache_filter_result(job.jobId, result)
            return result

        except Exception as e:
            logger.error(f"Error in detailed analysis: {str(e)}")
            logger.error(traceback.format_exc())
            result = JobStatusResponse(
                status=JobStatus.ERROR,
                match=False,
                reasons=[f"Error in analysis: {str(e)}"],
                title_score=title_score,
                filter_type=FilterType.DETAILED
            )
            return result

    async def clear_cache(self) -> None:
        """Clear the job information cache"""
        await self._job_cache.clear_cache()
