from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from uuid import uuid4
from pydantic import BaseModel

@dataclass
class GlassdoorRating:
    rating: float
    reviewCount: int
    isValid: bool

class VisaSupport(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED="UNSUPPORTED"
    UNKNOWN="UNKNOWN"

@dataclass
class JobInfo:
    jobId: str
    title: str
    company: str
    location: str
    glassdoorRating: GlassdoorRating

@dataclass
class JobDetailedInfo(JobInfo):
    description: str
    url: Optional[str] = None
    requirements: Optional[str] = None
    aboutCompany: str = ""
    companySize: str = ""

class FilterType(Enum):
    PRELIMINARY = "preliminary"
    DETAILED = "detailed"

@dataclass
class JobStatusResponse:
    status: str
    reasons: List[str] = field(default_factory=list)
    title_score: Optional[float] = None
    match: Optional[bool] = None
    filter_type: FilterType = FilterType.PRELIMINARY
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

# New additions for job application functionality
class ProcessingStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ApplyType(Enum):
    EASY = "easy_apply"
    EXTERNAL = "external"

class ApplicationPhase(Enum):
    RESUME = 'resume'
    COVER_LETTER = 'cover_letter'
    FINALIZED = 'finalized'

@dataclass
class CustomizedContent:
    """Content for both original and customized versions"""
    original: str
    customized: str

@dataclass
class ActiveTask:
    """Unified session/task data for application process"""
    job_id: str
    apply_type: ApplyType
    status: ProcessingStatus = ProcessingStatus.PENDING
    current_phase: ApplicationPhase = ApplicationPhase.RESUME
    error: Optional[str] = None
    resume_data: Optional[CustomizedContent] = None
    recommended_skills: Optional[List[str]] = None
    cover_letter_data: Optional[CustomizedContent] = None
    preview_data: Optional[str] = None  # Base64 encoded PNG data
    session_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class JobAnalysisInfo:
    """Stores the results of job requirement analysis from Claude"""
    skills_dict: Dict[str, Any]
    experience_dict: Dict[str, Any]
    red_flags_dict: Dict[str, Any]
    visa_support: VisaSupport
    post_language: str
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

class ApplyRequest(BaseModel):
    apply_type: ApplyType

# Add request model
class FinalizeRequest(BaseModel):
    session_id: str
    content: str
