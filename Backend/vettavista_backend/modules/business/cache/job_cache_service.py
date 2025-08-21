import asyncio
from datetime import datetime
from typing import Dict, Optional

from vettavista_backend.config import ResumeModel
from vettavista_backend.modules.models.services import JobDetailedInfo, JobAnalysisInfo, JobStatusResponse


class JobCacheService:
    """Service for managing cached job information"""
    
    def __init__(self):
        self._job_info_cache: Dict[str, JobDetailedInfo] = {}
        self._job_analysis_cache: Dict[str, JobAnalysisInfo] = {}
        self._resume_cache: Dict[str, ResumeModel] = {}
        self._cover_letter_cache: Dict[str, str] = {}
        self._filter_cache: Dict[str, JobStatusResponse] = {}
        self._cache_lock = asyncio.Lock()
    
    async def get_job_info(self, job_id: str) -> Optional[JobDetailedInfo]:
        """Get cached job information by ID"""
        return self._job_info_cache.get(job_id)
    
    async def set_job_info(self, job_id: str, info: JobDetailedInfo) -> None:
        """Store job information in cache"""
        self._job_info_cache[job_id] = info
    
    async def get_job_analysis(self, job_id: str) -> Optional[JobAnalysisInfo]:
        """Get cached job analysis info by job ID"""
        async with self._cache_lock:
            return self._job_analysis_cache.get(job_id)

    async def set_job_analysis(self, job_id: str, analysis: JobAnalysisInfo) -> None:
        """Cache job analysis info"""
        async with self._cache_lock:
            self._job_analysis_cache[job_id] = analysis 

    async def get_customized_resume(self, job_id: str) -> Optional[ResumeModel]:
        """Get customized resume from cache"""
        return self._resume_cache.get(job_id)

    async def set_customized_resume(self, job_id: str, resume: ResumeModel) -> None:
        """Set customized resume in cache"""
        self._resume_cache[job_id] = resume 

    async def get_cover_letter(self, job_id: str) -> Optional[str]:
        """Get cached cover letter content"""
        return self._cover_letter_cache.get(job_id)

    async def set_cover_letter(self, job_id: str, content: str) -> None:
        """Cache cover letter content"""
        self._cover_letter_cache[job_id] = content

    async def get_filter_result(self, job_id: str) -> Optional[JobStatusResponse]:
        """Get cached filter result for a job."""
        if job_id not in self._filter_cache:
            return None
            
        # Remove results older than 24 hours
        cached = self._filter_cache[job_id]
        if datetime.now().timestamp() - cached.timestamp > 604800:
            del self._filter_cache[job_id]
            return None
            
        return cached
        
    async def set_filter_result(self, job_id: str, result: JobStatusResponse) -> None:
        """Cache filter result for a job."""
        if result.status != "error":  # Don't cache error results
            self._filter_cache[job_id] = result

    async def clear_cache(self) -> None:
        """Clear all cached data"""
        async with self._cache_lock:
            self._job_info_cache.clear()
            self._job_analysis_cache.clear()
            self._resume_cache.clear()
            self._cover_letter_cache.clear()
            self._filter_cache.clear()