from typing import Protocol, Dict, Tuple

from vettavista_backend.config import ResumeModel
from vettavista_backend.modules.business.cache.job_cache_service import JobCacheService
from vettavista_backend.modules.models.services import JobDetailedInfo, VisaSupport


class ClaudeServiceProtocol(Protocol):
    async def customize_resume(self, job_info: JobDetailedInfo, job_cache: JobCacheService) -> Tuple[ResumeModel, ResumeModel]:
        ...
        
    async def customize_cover_letter(self, customized_resume_latex: str, job_info: JobDetailedInfo, job_cache: JobCacheService) -> str:
        ...

    async def batch_extract_job_info(self, job_description: str, post_lang: str) -> Tuple[Dict, Dict, Dict, VisaSupport]:
        ... 