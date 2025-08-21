import logging
from datetime import datetime
from typing import Dict, Optional

from vettavista_backend.config.global_constants import JobStatus
from vettavista_backend.modules.models.services import JobStatusResponse
from vettavista_backend.modules.storage import BlacklistStorage, JobHistoryStorage
from vettavista_backend.modules.business.cache.job_cache_service import JobCacheService

logger = logging.getLogger(__name__)

class BaseFilterService:
    """Base class for filter models with common functionality."""
    
    def __init__(
        self,
        blacklist_storage: BlacklistStorage,
        job_history_storage: JobHistoryStorage,
        job_cache: JobCacheService
    ):
        """Initialize the filter service with its components."""
        self.blacklist_storage = blacklist_storage
        self.job_history_storage = job_history_storage
        self._job_cache = job_cache
        logger.info("BaseFilterService initialized")
        
    async def get_cached_result(self, job_id: str) -> Optional[JobStatusResponse]:
        """Get cached filter result for a job."""
        result = await self._job_cache.get_filter_result(job_id)
        if result is None:
            logger.info(f"Cache miss for job {job_id}")
        else:
            logger.info(f"Cache hit for job {job_id}: {result}")
        return result
        
    async def cache_filter_result(self, job_id: str, result: JobStatusResponse) -> None:
        """Cache filter result for a job."""
        logger.info(f"Caching result for job {job_id}: {result}")
        await self._job_cache.set_filter_result(job_id, result)
        
    async def clear_cache(self) -> None:
        """Clear the filter cache."""
        await self._job_cache.clear_cache() 