import logging
from dataclasses import asdict
from typing import Dict, List

from vettavista_backend.modules.api.rest.base import BaseRESTEndpoint
from vettavista_backend.modules.api.utils import handle_endpoint_errors
from vettavista_backend.modules.business.filter import PreliminaryFilterService, DetailedFilterService
from vettavista_backend.modules.models.services import JobInfo, JobDetailedInfo
from vettavista_backend.modules.utils import decode_dataclass

logger = logging.getLogger(__name__)

class FilterEndpoints(BaseRESTEndpoint):
    def __init__(self, preliminary_filter_service: PreliminaryFilterService, detailed_filter_service: DetailedFilterService):
        self.preliminary_filter_service = preliminary_filter_service
        self.detailed_filter_service = detailed_filter_service
        super().__init__()
    
    def setup_routes(self) -> None:
        @self.router.post("/api/preliminary-filter")
        @handle_endpoint_errors
        async def preliminary_filter(job_data_list: List[Dict]):
            """Quick filtering based on job title and location"""
            logger.info(f"\n=== Preliminary Filter Request ===")
            logger.info(f"Number of jobs to filter: {len(job_data_list)}")
            
            # Convert dicts to JobInfo objects with nested decoding
            jobs = [decode_dataclass(JobInfo, job_data) for job_data in job_data_list]
            
            # Get filter results
            results = await self.preliminary_filter_service.preliminary_filter(jobs)
            
            # Convert responses to dicts
            return [asdict(result) for result in results]
        
        @self.router.post("/api/detailed-filter")
        @handle_endpoint_errors
        async def detailed_filter(job_data: Dict):
            """Detailed filtering using Claude for skill analysis"""
            logger.info(f"\n=== Detailed Filter Request ===")
            logger.info(f"Job ID: {job_data.get('jobId')}")
            logger.info(f"Title: {job_data.get('title')}")
            logger.info(f"Company: {job_data.get('company')}")
            logger.info(f"Company Size: {job_data.get('companySize')}")
            logger.info(f"About Company Length: {len(job_data.get('aboutCompany', ''))}")
            logger.info(f"Description Length: {len(job_data.get('description', ''))}")
            
            # Convert dict to JobDetailedInfo
            job = decode_dataclass(JobDetailedInfo, job_data)
            
            # Get filter result
            result = await self.detailed_filter_service.detailed_filter(job)
            
            # Convert response to dict
            return asdict(result)