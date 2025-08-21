from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from vettavista_backend.config.global_constants import JobStatus, ApplicationStatus


@dataclass
class BlacklistEntry:
    """Data model for blacklisted company entries"""
    company: str
    reason: str = ""
    notes: str = ""
    date_created: str = field(default_factory=lambda: datetime.now().isoformat())
    date_updated: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class JobHistoryEntry:
    """Data model for job history entries"""
    job_id: str
    title: str = ""
    company: str = ""
    location: str = ""
    url: str = ""
    match_status: str = JobStatus.UNKNOWN
    application_status: str = ApplicationStatus.NEW
    rejection_reason: str = ""
    skip_reason: str = ""
    user_notes: str = ""
    date_created: str = field(default_factory=lambda: datetime.now().isoformat())
    date_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    date_applied: Optional[str] = None
    date_rejected: Optional[str] = None
    resume_path: Optional[str] = None
    cover_letter_path: Optional[str] = None