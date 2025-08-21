import logging
import os
from dataclasses import asdict
from typing import Optional, List

from platformdirs import user_documents_dir

from vettavista_backend.config import APP_NAME
from vettavista_backend.config.global_constants import STORAGE_SETTINGS
from vettavista_backend.modules.models.storage import BlacklistEntry
from vettavista_backend.modules.storage.csv_storage import CSVStorageService
from vettavista_backend.modules.utils import block_base_methods

logger = logging.getLogger(__name__)

@block_base_methods(allowed_methods=["start_backup_scheduler", "stop_backup_scheduler"])
class BlacklistStorage(CSVStorageService):
    """Storage service for blacklisted companies"""
    
    def __init__(self):
        super().__init__(
            file_path=os.path.join(user_documents_dir(), APP_NAME, STORAGE_SETTINGS['blacklist_file']),
            key_column='company',
            data_class=BlacklistEntry,
            backup_enabled=True
        )
        
    async def add_company(self, company: str, reason: str = "", notes: str = "") -> None:
        """Add a company to the blacklist"""
        entry = BlacklistEntry(
            company=company,
            reason=reason,
            notes=notes
        )
        await self.set(company, asdict(entry))
        
    async def remove_company(self, company: str) -> None:
        """Remove a company from the blacklist"""
        await self.delete(company)
        
    async def is_blacklisted(self, company: str) -> bool:
        """Check if a company is blacklisted"""
        return await self.get(company) is not None
        
    async def get_company(self, company: str) -> Optional[BlacklistEntry]:
        """Get details for a blacklisted company"""
        data = await self.get(company)
        return BlacklistEntry(**data) if data else None
        
    async def update_notes(self, company: str, notes: str) -> None:
        """Update notes for a blacklisted company"""
        entry = await self.get_company(company)
        if entry:
            entry.notes = notes
            await self.set(company, asdict(entry))
            
    async def get_all_companies(self) -> List[BlacklistEntry]:
        """Get all blacklisted companies"""
        data = await self.get_all()
        return [BlacklistEntry(**item) for item in data] 