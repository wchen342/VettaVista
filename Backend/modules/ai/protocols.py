from typing import Protocol, Dict, Union, AsyncGenerator, Tuple, List, Any
from config import ResumeModel
from modules.models.services import JobDetailedInfo, VisaSupport
from modules.business.cache.job_cache_service import JobCacheService

class ClaudeServiceProtocol(Protocol):
    async def customize_resume(self, job_info: JobDetailedInfo, job_cache: JobCacheService) -> Tuple[ResumeModel, ResumeModel]:
        ...
        
    async def customize_cover_letter(self, customized_resume_latex: str, job_info: JobDetailedInfo, job_cache: JobCacheService) -> str:
        ...

    async def batch_extract_job_info(self, job_description: str, post_lang: str) -> Tuple[Dict, Dict, Dict, VisaSupport]:
        ... 