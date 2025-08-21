from abc import ABC, abstractmethod
from typing import List, Optional

from vettavista_backend.modules.models.services import JobInfo, JobDetailedInfo, JobStatusResponse


class FilterService(ABC):
    """Base interface for filter models."""
    
    @abstractmethod
    async def preliminary_filter(self, jobs: List[JobInfo]) -> List[JobStatusResponse]:
        """Quick filtering based on job title and location."""
        pass
        
    @abstractmethod
    async def detailed_filter(self, job: JobDetailedInfo, use_streaming: bool = False) -> JobStatusResponse:
        """Detailed filtering using AI for skill analysis."""
        pass
        
    @abstractmethod
    def get_cached_result(self, job_id: str) -> Optional[JobStatusResponse]:
        """Get cached filter result for a job."""
        pass
        
    @abstractmethod
    def cache_filter_result(self, job_id: str, result: JobStatusResponse) -> None:
        """Cache filter result for a job."""
        pass
        
    @abstractmethod
    def clear_cache(self) -> None:
        """Clear the filter cache."""
        pass
