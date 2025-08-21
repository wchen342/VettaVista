import logging
import os
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import List, Optional

from platformdirs import user_documents_dir

from vettavista_backend.config.global_constants import (
    STORAGE_SETTINGS, ApplicationStatus, APP_NAME
)
from vettavista_backend.modules.models.storage import JobHistoryEntry
from vettavista_backend.modules.storage.csv_storage import CSVStorageService
from vettavista_backend.modules.utils import block_base_methods

logger = logging.getLogger(__name__)

@block_base_methods(allowed_methods=["start_backup_scheduler", "stop_backup_scheduler"])
class JobHistoryStorage(CSVStorageService):
    """Storage service for job application history"""
    
    def __init__(self):
        super().__init__(
            file_path=os.path.join(user_documents_dir(), APP_NAME, STORAGE_SETTINGS['history_file']),
            key_column='job_id',
            data_class=JobHistoryEntry,
            backup_enabled=True
        )
            
    async def add_or_update_job(self, entry: JobHistoryEntry) -> None:
        """Add or update a job in the history"""
        entry.date_updated = datetime.now().isoformat()
        await self.set(entry.job_id, asdict(entry))
        
    async def update_application_status(self, job_id: str, status: str, notes: str = "") -> None:
        """Update application status and add notes"""
        entry = await self.get_job(job_id)
        if entry:
            now = datetime.now().isoformat()
            entry.application_status = status
            entry.date_updated = now
            
            # Update specific date fields
            if status == ApplicationStatus.APPLIED:
                entry.date_applied = now
            elif status == ApplicationStatus.REJECTED:
                entry.date_rejected = now
                
            await self.set(job_id, asdict(entry))
            
            # Add notes if provided
            if notes:
                await self.update_notes(job_id, notes)
                
    async def add_rejection(self, job_id: str, reason: str = "") -> None:
        """Add rejection details to a job"""
        entry = await self.get_job(job_id)
        if entry:
            now = datetime.now().isoformat()
            entry.application_status = ApplicationStatus.REJECTED
            entry.rejection_reason = reason
            entry.date_rejected = now
            entry.date_updated = now
            await self.set(job_id, asdict(entry))

    async def is_rejected(self, job_id: str) -> bool:
        """Check if a job application was rejected"""
        entry = await self.get_job(job_id)
        if not entry:
            return False
        return entry.application_status == ApplicationStatus.REJECTED
            
    async def update_notes(self, job_id: str, notes: str) -> None:
        """Update notes for a job"""
        entry = await self.get_job(job_id)
        if entry:
            entry.user_notes = notes
            await self.set(job_id, asdict(entry))
            
    async def get_job(self, job_id: str) -> Optional[JobHistoryEntry]:
        """Get a job by ID"""
        data = await self.get(job_id)
        return JobHistoryEntry(**data) if data else None
            
    async def search_jobs(self, query: str = "", status: str = None, days: int = None) -> List[JobHistoryEntry]:
        """Search jobs with text query and/or status filter"""
        filter_params = {}
        if status:
            filter_params['application_status'] = status
            
        jobs = await self.query(filter_params)
        entries = [JobHistoryEntry(**job) for job in jobs]
        
        # Filter by date if specified
        if days is not None:
            cutoff = datetime.now() - timedelta(days=days)
            entries = [
                entry for entry in entries 
                if datetime.fromisoformat(entry.date_applied) > cutoff
            ]
            
        # Filter by text query if specified
        if query:
            query = query.lower()
            entries = [
                entry for entry in entries
                if query in entry.title.lower() or
                   query in entry.company.lower() or
                   query in entry.location.lower()
            ]
            
        return entries