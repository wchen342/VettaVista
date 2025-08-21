"""
Configuration models for the application.
These dataclasses match the structure of YAML config files and their usage in the code.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

@dataclass(frozen=True)
class Education:
    degree: str
    university: str
    extra: str
    start: datetime  # Will be formatted as YYYY-MM when used
    graduation: datetime  # Will be formatted as YYYY-MM when used

@dataclass(frozen=True)
class PersonalsModel:
    # Contact info
    email: str
    first_name: str
    middle_name: str
    last_name: str
    phone: str
    
    # Location
    current_city: str
    street: str
    state: str
    zipcode: str
    country: str

@dataclass(frozen=True)
class ExperienceEntry:
    title: str
    start: datetime  # Will be formatted as YYYY-MM when used
    end: datetime  # datetime.max represents "Present"
    organization: str  # Note: this matches the field name in YAML
    location: str
    details: List[str]
    _exp_id: Optional[str] = field(default=None, init=False)  # Private field for ID

    @property
    def exp_id(self) -> Optional[str]:
        """Get the experience ID."""
        return self._exp_id

    def set_id(self, value: str) -> None:
        """Set the experience ID."""
        object.__setattr__(self, '_exp_id', value)

@dataclass(frozen=True)
class ProjectEntry:
    name: str
    details: List[str]
    _proj_id: Optional[str] = field(default=None, init=False)  # Private field for ID

    @property
    def proj_id(self) -> Optional[str]:
        """Get the project ID."""
        return self._proj_id

    def set_id(self, value: str):
        """Set the project ID"""
        object.__setattr__(self, '_proj_id', value)

@dataclass(frozen=True)
class ResumeModel:
    # Profile
    website: str
    linkedIn: str

    # Skills section
    skills: Dict[str, List[str]]

    # Experience and projects
    experience: List[ExperienceEntry]
    projects: List[ProjectEntry]

    # Education
    highest_degree: str
    educations: List[Education]
    did_masters: bool

    # Cover Letter Template
    cover_letter_template: Optional[str]

@dataclass(frozen=True)
class SecretsModel:
    claude_api_key: str

@dataclass(frozen=True)
class SearchModel:
    # Job preferences
    preferred_titles: List[str]
    bad_words: List[str]
    skip_required_skill: List[str]

    # Language detection
    lang_detect_remove_words: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class AISettingModel:
    # Claude Settings
    # Temperature settings
    claude_extraction_temperature: float
    claude_customization_temperature: float

    # Token limitations
    claude_max_tokens: int
    claude_thinking_budget_tokens: int

    # Other settings
    claude_thinking: bool

@dataclass(frozen=True)
class AIPromptsModel:
    # Claude Prompts
    claude_extraction_prompt_base: str
    claude_experience_rules: str
    claude_skills_rules: str
    claude_visa_rules: str
    claude_scoring_rules: str

    claude_resume_init: str
    claude_cultural_contexts_dict: dict
    claude_cultural_context: str
    claude_resume_skills: str
    claude_resume_experience: str
    claude_resume_projects: str
    claude_cover_letter: str
