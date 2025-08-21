import asyncio
import logging
from typing import Dict

from vettavista_backend.modules.api.rest.base import BaseRESTEndpoint
from vettavista_backend.modules.api.utils import handle_endpoint_errors
from vettavista_backend.modules.storage.blacklist_storage import BlacklistStorage
from vettavista_backend.modules.sync.base import DataBroadcaster

logger = logging.getLogger(__name__)

class BlacklistEndpoints(BaseRESTEndpoint):
    def __init__(self, blacklist_storage: BlacklistStorage, broadcaster: DataBroadcaster):
        self.blacklist_storage = blacklist_storage
        self.broadcaster = broadcaster
        super().__init__()
    
    def setup_routes(self) -> None:
        @self.router.post("/api/blacklist")
        @handle_endpoint_errors
        async def add_to_blacklist(data: Dict):
            """Add company to blacklist."""
            company = data.get('company')
            if not company:
                raise ValueError("Company name required")
            
            reason = data.get('reason', '')
            notes = data.get('notes', '')
            await self.blacklist_storage.add_company(company, reason=reason, notes=notes)
            
            # Add small delay to ensure storage operation completes
            await asyncio.sleep(0.1)
            blacklist = await self.blacklist_storage.get_all_companies()
            await self.broadcaster.broadcast_update({
                "blacklist": blacklist
            })
        
        @self.router.delete("/api/blacklist/{company}")
        @handle_endpoint_errors
        async def remove_from_blacklist(company: str):
            """Remove company from blacklist."""
            await self.blacklist_storage.remove_company(company)
            
            # Broadcast update to connected clients
            blacklist = await self.blacklist_storage.get_all_companies()
            await self.broadcaster.broadcast_update({
                "blacklist": blacklist
            })
        
        @self.router.get("/api/blacklist")
        @handle_endpoint_errors
        async def get_blacklist():
            """Get all blacklisted companies."""
            blacklist = await self.blacklist_storage.get_all()
            return {"blacklist": blacklist}