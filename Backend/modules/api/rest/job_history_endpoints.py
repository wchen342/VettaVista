from typing import Dict, Optional
from fastapi import HTTPException
from modules.api.rest.base import BaseRESTEndpoint
from modules.storage.job_history_storage import JobHistoryStorage
from modules.sync.base import DataBroadcaster
from modules.api.utils import handle_endpoint_errors
from config.global_constants import ApplicationStatus
import logging

logger = logging.getLogger(__name__)

class JobHistoryEndpoints(BaseRESTEndpoint):
    def __init__(self, job_history_storage: JobHistoryStorage, broadcaster: DataBroadcaster):
        self.job_history_storage = job_history_storage
        self.broadcaster = broadcaster
        super().__init__()
    
    def setup_routes(self) -> None:
        @self.router.post("/api/job-history")
        @handle_endpoint_errors
        async def add_or_update_job(job_data: Dict):
            """Add or update job in history."""
            if not all(k in job_data for k in ['jobId', 'title', 'company']):
                raise ValueError("Missing required fields: jobId, title, company")
            
            # Only store jobs that are being applied to
            if job_data.get('application_status') in [
                ApplicationStatus.APPLIED,
                ApplicationStatus.IN_PROGRESS,
                ApplicationStatus.OFFER,
                ApplicationStatus.ACCEPTED,
                ApplicationStatus.DECLINED
            ]:
                # Add/update job and broadcast to connected clients
                await self.job_history_storage.add_or_update_job(job_data)
                history = await self.job_history_storage.search_jobs(days=30)
                await self.broadcaster.broadcast_update({
                    "history": history
                })