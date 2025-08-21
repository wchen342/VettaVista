import logging
from typing import Dict, List, Tuple

import numpy as np
from rapidfuzz import fuzz

from vettavista_backend.config import resume, search
from vettavista_backend.config.global_constants import TITLE_MATCH_SETTINGS  # Reuse the same model
from vettavista_backend.modules.business.utils.base import SkillMatcher
from vettavista_backend.modules.business.utils.utils import batch_encode_strings, calculate_pairwise_similarities, \
    get_from_cache_symmetric, \
    load_model_prefer_cache

logger = logging.getLogger(__name__)

class SimpleSkillMatcher(SkillMatcher):
    def __init__(self):
        """Initialize the skill matcher with embedding model"""
        self.model = load_model_prefer_cache(TITLE_MATCH_SETTINGS['model_name'])
        self.fuzzy_threshold = 85  # Fuzzy match threshold
        self.embedding_threshold = 0.85  # Semantic similarity threshold

        # Update categories to match resume template
        self.skill_categories = [
            'programming languages',  # Space instead of underscore
            'frameworks',
            'mobile development',  # Space instead of underscore
            'other technical',
            'soft skills'  # Space instead of underscore
        ]
        
        # Initialize caches
        self.embedding_cache = {}
        self.match_cache = {}
        
        # Pre-compute resume skill embeddings
        resume_skills = []
        for category in self.skill_categories:
            if category in resume.skills:
                resume_skills.extend(resume.skills[category])
        
        # Use batch_encode_strings to compute and cache embeddings
        if resume_skills:
            logger.info(f"Pre-computing embeddings for {len(resume_skills)} resume skills")
            self.resume_skill_embeddings = batch_encode_strings(
                texts=resume_skills,
                model=self.model,
                embedding_cache=self.embedding_cache
            )
        
    def _get_semantic_match(self, skill1: str, skill2: str) -> float:
        """Get semantic similarity between two skills using embeddings"""
        embeddings = self.model.encode([skill1, skill2])
        similarity = np.dot(embeddings[0], embeddings[1]) / (
            np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
        )
        return float(similarity)
        
    def _batch_encode_job_skills(self, job_skills: Dict) -> Dict[str, np.ndarray]:
        """Batch encode all skills from job description"""
        required_skills = set()
        for category in self.skill_categories:
            if category in job_skills and job_skills[category]:
                required_skills.update(job_skills[category])
        
        if not required_skills:
            return {}
            
        return batch_encode_strings(
            texts=list(required_skills),
            model=self.model,
            embedding_cache=self.embedding_cache
        )
        
    def _batch_match_skills(self, candidate_skills: List[str], required_skills: List[str]) -> dict[
        tuple[str, str], tuple[bool, str, float]]:
        """Batch match all skills and return best matches"""
        # First calculate all fuzzy scores
        all_matches = {}  # (req, candidate) -> (matched, method, score)
        for req in required_skills:
            req_lower = req.lower()
            for candidate in candidate_skills:
                cand_lower = candidate.lower()
                cache_key = (cand_lower, req_lower)
                
                # Check cache first
                value = get_from_cache_symmetric(self.match_cache, cache_key)
                if value is not None:
                    match, method, score = value
                    all_matches[(req, candidate)] = (match, method, score)
                else:
                    # Calculate fuzzy score
                    score = fuzz.ratio(cand_lower, req_lower)
                    if score >= self.fuzzy_threshold:
                        all_matches[(req, candidate)] = (True, "fuzzy", score)
                        self.match_cache[cache_key] = (True, "fuzzy", score)
                    else:
                        all_matches[(req, candidate)] = (False, "none", score)
                        self.match_cache[cache_key] = (False, "none", score)
        
        # For skills without fuzzy matches, calculate semantic similarities
        reqs_needing_semantic = [req for req in required_skills 
                               if not any(all_matches.get((req, cand))[0] for cand in candidate_skills)]
        
        if reqs_needing_semantic:
            # Calculate all semantic similarities at once
            similarities = calculate_pairwise_similarities(
                embeddings1=batch_encode_strings(texts=reqs_needing_semantic, model=self.model, embedding_cache=self.embedding_cache),
                embeddings2=self.resume_skill_embeddings,
                similarity_cache=self.match_cache
            )
            
            # Process semantic similarities
            for req in reqs_needing_semantic:
                for candidate in candidate_skills:
                    sim = similarities.get((req, candidate))
                    if sim is not None:
                        score = sim * 100
                        if sim >= self.embedding_threshold:
                            all_matches[(req, candidate)] = (True, "semantic", score)
                            self.match_cache[(candidate.lower(), req.lower())] = (True, "semantic", score)
                        else:
                            # Update the score if it's better than fuzzy
                            old_match = all_matches.get((req, candidate))
                            if old_match and score > old_match[2]:
                                all_matches[(req, candidate)] = (False, "none", score)
                                self.match_cache[(candidate.lower(), req.lower())] = (False, "none", score)
        
        return all_matches

    def evaluate_skills_match(self, job_skills: Dict) -> Tuple[bool, List[str]]:
        """Evaluate if job skills match resume requirements"""
        logger.info("\n=== Skill Matching Analysis ===")

        # save reasons for match/no match
        reasons = []

        # First check language requirements
        if 'languages' in job_skills and job_skills['languages']['required']:
            resume_languages = set(lang.upper() for lang in resume.skills['languages'])
            required_languages = set(lang.upper() for lang in job_skills['languages']['required'])
            missing_languages = required_languages - resume_languages
            
            if missing_languages:
                logger.info(f"\nMissing required languages: {', '.join(missing_languages)}")
                return False, [f"Missing required languages: {', '.join(missing_languages)}"]
            logger.info(f"\nLanguage requirements met: {', '.join(required_languages)}")

        # Get candidate skills from resume (we already have their embeddings)
        candidate_skills = []
        candidate_skill_categories = {}  # Track which category each skill belongs to
        for category in self.skill_categories:
            if category in resume.skills:
                logger.info(f"\nResume skills in {category}: {', '.join(resume.skills[category])}")
                for skill in resume.skills[category]:
                    candidate_skills.append(skill)
                    candidate_skill_categories[skill] = category
        
        # Get required skills from job description
        required_skills = set()
        for category in self.skill_categories:
            if category in job_skills and job_skills[category] and category != 'soft skills':
                logger.info(f"\nJob required skills in {category}: {', '.join(job_skills[category])}")
                required_skills.update(job_skills[category])
        
        if not required_skills:
            logger.warning("No required skills found in job description")
            return False, ["No required skills found in job description"]
            
        logger.info(f"\nTotal required skills: {len(required_skills)}")

        # Filter for blacklisted skills
        for req in required_skills:
            for skip_skill in search.skip_required_skill:
                if req.lower() == skip_skill.lower():
                    logger.info(f"\nJob required skills is blacklisted: {req}")
                    return False, [f"Job required skills is blacklisted: {req}"]

        # Get all matches in batch
        all_matches = self._batch_match_skills(candidate_skills, list(required_skills))

        # Process matches to find best matches for each required skill
        matching_pairs = []
        missing_skills = []
        matches = 0

        # Structure to store matches by category
        matched_by_category = {category: [] for category in self.skill_categories}

        for req in required_skills:
            # Find best match for this requirement
            req_matches = [(cand, match_type, score) 
                          for (r, cand), (matched, match_type, score) in all_matches.items()
                          if r == req and matched]

            if req_matches:
                # Get the match with the highest score
                best_candidate, match_type, score = max(req_matches, key=lambda x: x[2])
                matches += 1
                matching_pairs.append(f"{req} ~ {best_candidate} ({match_type}: {score:.1f}%)")
                logger.info(f"✓ Matched: {req} ~ {best_candidate} ({match_type}: {score:.1f}%)")

                # Add to category-based structure
                category = candidate_skill_categories[best_candidate]
                matched_by_category[category].append((best_candidate, score/100))  # Convert score back to 0-1 range
            else:
                missing_skills.append(req)
                # Get the best non-matching score for logging
                best_score = 0.0
                for cand in candidate_skills:
                    cache_key = (cand.lower(), req.lower())
                    value = get_from_cache_symmetric(self.match_cache, cache_key)
                    if value is not None:
                        _, _, score = value
                        best_score = max(best_score, score)
                logger.info(f"✗ No match for: {req} (best score: {best_score:.1f}%)")

        if matching_pairs:
            reasons.append(f"Matching skills: {', '.join(matching_pairs)}")
        if missing_skills:
            reasons.append(f"Missing skills: {', '.join(missing_skills)}")

        match_ratio = float(matches) / len(required_skills)  # Ensure Python float
        logger.info(f"\nMatch ratio: {match_ratio:.1%} ({matches}/{len(required_skills)} skills)")

        return match_ratio >= 0.5, reasons