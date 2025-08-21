import logging
from typing import List, Union, Tuple, Dict

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from vettavista_backend.config.global_constants import TITLE_MATCH_SETTINGS
from vettavista_backend.modules.business.utils.base import TitleMatcher
from vettavista_backend.modules.business.utils.utils import batch_encode_strings, batch_encode_grouped_strings, calculate_pairwise_similarities, \
    find_best_match_from_cache, load_model_prefer_cache

logger = logging.getLogger(__name__)

class SentenceTransformerMatcher(TitleMatcher):
    def __init__(self, preferred_titles: List[str]):
        """
        preferred_titles: Simple list like 
        ["Software Engineer", "Software Developer", "Python Developer"]
        """
        # Load a lightweight model suitable for semantic similarity
        self.model = load_model_prefer_cache(TITLE_MATCH_SETTINGS['model_name'])
        # Pre-compute embeddings for preferred titles
        self.preferred_embeddings = self.model.encode(preferred_titles)
        # Initialize cache
        self.cache = {}
        self.preferred_titles = preferred_titles  # Store for logging
        logger.info(f"TitleMatcher initialized with {len(preferred_titles)} preferred titles")
        
    def match_title(self, job_title: str) -> float:
        """Returns similarity score 0-1"""
        logger.info(f"\n=== Title Matching for: {job_title} ===")
        
        # Check cache first
        if job_title in self.cache:
            score = self.cache[job_title]
            logger.info(f"Cache hit! Score: {score:.3f}")
            return score
            
        # Get embedding for job title
        job_embedding = self.model.encode([job_title])[0]
        # Calculate cosine similarities with all preferred titles
        similarities = np.dot(self.preferred_embeddings, job_embedding) / (
            np.linalg.norm(self.preferred_embeddings, axis=1) * np.linalg.norm(job_embedding)
        )
        
        # Log individual similarities
        for i, score in enumerate(similarities):
            logger.info(f"Similarity with '{self.preferred_titles[i]}': {score:.3f}")
        
        # Get highest similarity
        score = float(np.max(similarities))
        logger.info(f"Best match score: {score:.3f}")
        
        # Cache the result if cache not full
        if len(self.cache) < TITLE_MATCH_SETTINGS['cache_size']:
            self.cache[job_title] = score
            
        return score

class AdvancedEmbeddingMatcher(TitleMatcher):
    def __init__(self, preferred_titles: List[str], temperature=0.8):
        """
        preferred_titles: Simple list like 
        ["Software Engineer", "Software Developer", "Python Developer"]
        """
        print(f"Loading model: {TITLE_MATCH_SETTINGS['model_name']}")
        self.model = load_model_prefer_cache(TITLE_MATCH_SETTINGS['model_name'])
        self.temperature = temperature
        self.preferred_titles = preferred_titles
        self.cache = {}  # For score cache
        self.embedding_cache = {}  # For embedding cache

        # Define domain prototypes with multiple examples
        self.domain_prototypes = {
            'frontend': [
                "Frontend web development",
                "UI development",
                "Client-side programming",
                "Web interface design",
                "Browser application development",
                "HTML CSS JavaScript development",
                "React Vue Angular development",
                "User interface engineering",
                "Frontend Entwickler",  # German
                "Web-Frontend-Entwickler",
                "UI-Entwickler",
                "Webentwickler Frontend"
            ],
            'backend': [
                "Backend server development",
                "Database management",
                "Server-side programming",
                "API development",
                "System architecture",
                "Database design",
                "Server infrastructure",
                "Microservices development",
                "Backend-Entwickler",  # German
                "Server-Entwickler",
                "Datenbankentwickler",
                "Backend-Systemarchitekt"
            ],
            'mobile': [
                "Mobile app development",
                "iOS development",
                "Android development",
                "React Native development",
                "Flutter development",
                "Mobile application engineer",
                "Smartphone app developer",
                "Cross-platform mobile development",
                "Mobile-App-Entwickler",  # German
                "Android-Entwickler",
                "iOS-Entwickler",
                "App-Entwickler"
            ],
            'devops': [
                "DevOps Engineer managing infrastructure",
                "Site Reliability Engineer",
                "Cloud Infrastructure Engineer",
                "Platform Engineer",
                "Systems Operations Engineer",
                "DevOps-Ingenieur",  # German
                "System-Administrator",
                "Cloud-Infrastruktur-Ingenieur",
                "Platform-Engineer"
            ],
            'data': [
                "Data Scientist working on ML models",
                "Machine Learning Engineer",
                "AI Research Engineer",
                "Data Engineer",
                "Analytics Engineer",
                "Data Scientist",  # German
                "Dateningenieur",
                "KI-Entwickler",
                "Machine-Learning-Ingenieur"
            ],
            'fullstack': [
                "Full Stack Developer",
                "Full Stack Web Engineer",
                "End-to-end Developer",
                "Full Stack Application Engineer",
                "Web Development Generalist",
                "Fullstack-Entwickler",  # German
                "Vollstack-Entwickler",
                "Full-Stack-Webentwickler",
                "Allstack-Entwickler"
            ]
        }

        # Add general software engineering patterns
        self.general_patterns = [
            'software engineer', 'software developer', 'programmer',
            'entwickler', 'softwareentwickler', 'programmierer',  # German
            '软件工程师', 'ソフトウェアエンジニア',  # Chinese/Japanese
            'engineer', 'developer'  # Generic terms when not with specific domain
        ]

        print("Computing domain embeddings...")
        # Pre-compute embeddings for domain prototypes using batch_encode_grouped_strings
        self.domain_embeddings = batch_encode_grouped_strings(
            text_groups=self.domain_prototypes,
            model=self.model,
            embedding_cache=self.embedding_cache
        )
        
        # Pre-compute embeddings for preferred titles using batch_encode_strings
        self.preferred_embeddings = batch_encode_strings(
            texts=preferred_titles,
            model=self.model,
            embedding_cache=self.embedding_cache
        )
        # Convert preferred embeddings to numpy array for later use
        self.preferred_embeddings = np.stack([self.preferred_embeddings[t] for t in preferred_titles])

        # Domain relationship weights
        self.domain_relationships = {
            ('frontend', 'fullstack'): 0.3,
            ('backend', 'fullstack'): 0.3,
            ('backend', 'devops'): 0.2,
            ('data', 'backend'): 0.2,
            ('mobile', 'frontend'): 0.3,
            ('mobile', 'fullstack'): 0.2,
            # General role relationships
            ('general', 'frontend'): 0.2,  # General roles can do frontend
            ('general', 'backend'): 0.2,  # General roles can do backend
            ('general', 'fullstack'): 0.3,  # Strong relationship with fullstack
            ('general', 'mobile'): 0.2,  # Can transition to mobile
            ('general', 'devops'): 0.2,  # Can transition to devops
            ('general', 'data'): 0.1  # Harder transition to data
        }

        self.seniority_levels = {
            'junior': 1,
            'associate': 1,
            'mid': 2,
            'senior': 3,
            'staff': 4,
            'principal': 5,
            'lead': 4,
            'architect': 5,
            'head': 5,
            'director': 5
        }

    def get_domain_similarity(self, embedding, domain):
        """Calculate similarity with domain prototype"""
        domain_emb = self.domain_embeddings[domain]
        return cosine_similarity([embedding], [domain_emb])[0][0]

    def is_general_role(self, title):
        """Check if the title represents a general software engineering role"""
        title_lower = title.lower()

        # Check if it's a general role
        is_general = any(pattern in title_lower for pattern in self.general_patterns)

        # Make sure it's not actually a specific role
        specific_terms = [
            'frontend', 'front-end', 'backend', 'back-end',
            'mobile', 'ios', 'android', 'data', 'devops', 'fullstack',
            'ui', 'ux', 'database', 'ml', 'ai'
        ]
        is_specific = any(term in title_lower for term in specific_terms)

        return is_general and not is_specific

    def get_domain(self, title):
        """Get domain using semantic similarity with confidence check"""
        # First check if it's a general role
        if self.is_general_role(title):
            return 'general'

        """Get domain using semantic similarity with confidence check"""
        title_lower = title.lower()

        # Direct keyword matching first
        if any(term in title_lower for term in [
            'ui', 'ux', 'frontend', 'front-end', 'front end', '前端',
            'frontend-entwickler', 'ui-entwickler'
        ]):
            return 'frontend'
        elif any(term in title_lower for term in [
            'backend', 'back-end', 'back end', 'database', 'server', '后端',
            'backend-entwickler', 'datenbankentwickler'
        ]):
            return 'backend'
        elif any(term in title_lower for term in [
            'mobile', 'ios', 'android', 'flutter', 'react native', 'app developer',
            'mobile-app', 'app-entwickler', 'android-entwickler', 'ios-entwickler'
        ]):
            return 'mobile'

        # Semantic similarity check
        title_emb = self.encode([title])[0]
        similarities = {
            domain: self.get_domain_similarity(title_emb, domain)
            for domain in self.domain_prototypes.keys()
        }

        # Sort similarities in descending order
        sorted_sims = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        best_domain, best_sim = sorted_sims[0]

        # Only fall back to 'general' if really uncertain
        if best_sim < 0.3:
            return 'general'

        return best_domain

    def get_seniority(self, titles: Union[str, List[str]]) -> Union[int, np.ndarray]:
        """Get seniority levels for titles using vectorized operations"""
        # Handle single title case
        if isinstance(titles, str):
            titles = [titles]
            single_result = True
        else:
            single_result = False
            
        # Convert all titles to lowercase once
        titles_lower = np.array([t.lower() for t in titles])
        
        # Create a matrix of boolean masks for each seniority level
        # Shape: (num_titles, num_levels)
        level_masks = np.array([[level in title for title in titles_lower] 
                              for level in self.seniority_levels.keys()])
        
        # Convert levels to values array
        level_values = np.array(list(self.seniority_levels.values()))
        
        # Multiply masks with values and take max along levels axis
        # Shape: (num_titles,)
        max_levels = np.max(level_masks.T * level_values, axis=1)
        
        return max_levels[0] if single_result else max_levels
        
    def get_seniority_penalties(self, titles1: List[str], titles2: List[str]) -> np.ndarray:
        """Calculate seniority penalties for all pairs using vectorized operations"""
        seniorities1 = self.get_seniority(titles1)
        seniorities2 = self.get_seniority(titles2)
        
        # Calculate differences using broadcasting
        seniority_diffs = np.abs(seniorities1[:, np.newaxis] - seniorities2)
        return np.minimum(0.2, seniority_diffs * 0.1)

    def encode(self, texts):
        """Encode texts with caching."""
        # For single text, convert to list
        single_text = isinstance(texts, str)
        if single_text:
            texts = [texts]
        
        # Get uncached texts
        uncached = [t for t in texts if t not in self.embedding_cache]
        
        # Encode uncached texts
        if uncached:
            embeddings = self.model.encode(uncached)
            embeddings = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8) * self.temperature
            # Cache the new embeddings
            for text, emb in zip(uncached, embeddings):
                self.embedding_cache[text] = emb
        
        # Return embeddings in original order
        result = np.array([self.embedding_cache[t] for t in texts])
        return result[0] if single_text else result

    def get_domain_penalties(self, domains1: List[str], domains2: List[str]) -> np.ndarray:
        """Calculate domain penalties for all pairs using vectorized operations"""
        n1, n2 = len(domains1), len(domains2)
        penalties = np.full((n1, n2), 0.4)  # Default strong penalty
        
        for i, d1 in enumerate(domains1):
            for j, d2 in enumerate(domains2):
                if d1 == 'general' or d2 == 'general':
                    if d1 == d2:  # Both general
                        penalties[i, j] = 0.0
                    else:
                        specific_domain = d2 if d1 == 'general' else d1
                        rel_key = tuple(sorted(['general', specific_domain]))
                        penalties[i, j] = 0.3 - self.domain_relationships.get(rel_key, 0.2)
                else:
                    rel_key = tuple(sorted([d1, d2]))
                    if rel_key in self.domain_relationships:
                        penalties[i, j] = 0.3 - self.domain_relationships[rel_key]
        
        return penalties
        
    def get_similarity_with_preferred(self, job_title: str) -> List[Tuple[float, Dict]]:
        """Optimized version of get_similarity that uses pre-calculated preferred embeddings"""
        # Get domains
        job_domain = self.get_domain(job_title)
        preferred_domains = [self.get_domain(t) for t in self.preferred_titles]
        
        # Calculate base similarities using batch operations with pre-calculated embeddings
        job_embedding = batch_encode_strings([job_title], self.model, self.embedding_cache)
        
        # Pre-calculate penalties once
        domain_penalties = self.get_domain_penalties([job_domain], preferred_domains)
        seniority_penalties = self.get_seniority_penalties([job_title], self.preferred_titles)
        
        def adjust_similarities(sim_matrix: np.ndarray) -> np.ndarray:
            adjusted = sim_matrix - domain_penalties - seniority_penalties
            return np.maximum(0.1, adjusted)
        
        # Use pre-calculated preferred embeddings
        similarities = calculate_pairwise_similarities(
            embeddings1=job_embedding,
            embeddings2={t: emb for t, emb in zip(self.preferred_titles, self.preferred_embeddings)},
            matrix_fn=adjust_similarities,
            similarity_cache=self.cache
        )
        
        # Prepare results with details
        results = []
        for j, t2 in enumerate(self.preferred_titles):
            sim = similarities[(job_title, t2)]
            # Use pre-calculated penalties
            domain_penalty = domain_penalties[0, j]
            seniority_penalty = seniority_penalties[0, j]
            base_sim = sim + domain_penalty + seniority_penalty
            
            results.append((sim, {
                'base_similarity': base_sim,
                'domain1': job_domain,
                'domain2': preferred_domains[j],
                'domain_penalty': domain_penalty,
                'seniority_penalty': seniority_penalty
            }))
        
        return results

    def match_title(self, job_title: str) -> float:
        """Returns similarity score 0-1"""
        logger.info(f"\n=== Title Matching for: {job_title} ===")
        
        # Check cache first - try each preferred title
        score, match = find_best_match_from_cache(self.cache, job_title, self.preferred_titles)
        if match is not None:
            logger.info(f"Cache hit! Score: {score:.3f}")
            return score
        
        # Calculate similarities using optimized method
        similarities = self.get_similarity_with_preferred(job_title)
            
        # Find best match
        best_score = 0.0
        best_match = None
        for i, (score, details) in enumerate(similarities):
            if score > best_score:
                best_score = float(score)
                best_match = self.preferred_titles[i]
                
        logger.info(f"Best match: '{best_match}' with score: {best_score:.3f}")
        
        # Cache the result with tuple key if cache not full
        if len(self.cache) < TITLE_MATCH_SETTINGS['cache_size']:
            self.cache[(job_title, best_match)] = best_score
            
        return best_score