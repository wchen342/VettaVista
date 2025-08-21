from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

class TitleMatcher(ABC):
    """Base interface for job title matching."""
    
    @abstractmethod
    def match_title(self, job_title: str) -> float:
        """Returns similarity score 0-1."""
        pass

class LanguageDetector(ABC):
    """Base interface for language detection."""
    
    @abstractmethod
    def detect_language(self, text: str, k: int = 3) -> Tuple[Optional[str], float]:
        """Detect language of text with confidence score."""
        pass

class SkillMatcher(ABC):
    """Base interface for skill matching."""
    
    @abstractmethod
    def evaluate_skills_match(self, skills: Dict) -> Tuple[bool, List[str], Dict]:
        """Evaluate if skills match requirements."""
        pass
