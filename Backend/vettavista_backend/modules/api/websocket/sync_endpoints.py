import json
import logging
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect, APIRouter

from vettavista_backend.modules.api.websocket.base import WebSocketEndpoint
from vettavista_backend.modules.storage.blacklist_storage import BlacklistStorage
from vettavista_backend.modules.storage.job_history_storage import JobHistoryStorage
from vettavista_backend.modules.sync.websocket_manager import WebSocketSyncManager
from vettavista_backend.modules.utils import DataClassJSONEncoder

logger = logging.getLogger(__name__)

class SyncEndpoints(WebSocketEndpoint):
    """WebSocket endpoints for syncing data between server and client."""
    
    def __init__(self):
        self.job_history = JobHistoryStorage()
        self.blacklist = BlacklistStorage()
        self.manager = WebSocketSyncManager(blacklist_storage=self.blacklist, job_history_storage=self.job_history)
        self.router = APIRouter()
        self.setup_routes()
        
    def setup_routes(self):
        """Setup routes for sync endpoints"""
        @self.router.websocket("/ws/sync/{client_id}")
        async def websocket_endpoint(websocket: WebSocket, client_id: str):
            try:
                await self.handle_connection(websocket, client_id)
                
                while True:
                    try:
                        data = await websocket.receive_json()
                        await self.handle_message(client_id, data)
                    except WebSocketDisconnect:
                        await self.disconnect(client_id)
                        break
                    except Exception as e:
                        logger.error(f"Error handling message from client {client_id}: {e}")
                        await websocket.close(code=1011)  # Internal Error
                        break
                        
            except Exception as e:
                logger.error(f"Error in websocket connection: {e}")
                if websocket.client_state.CONNECTED:
                    await websocket.close(code=1011)
                await self.manager.unregister_client(client_id)
            
    async def handle_connection(self, websocket: WebSocket, client_id: str) -> None:
        """Handle new WebSocket connection."""
        try:
            await self.manager.connect(client_id, websocket)
            logger.info(f"Client {client_id} connected successfully")
            
            # Send initial sync data through broadcast
            sync_data = await self._get_sync_data()
            await self.manager.broadcast_update(sync_data)
        except Exception as e:
            logger.error(f"Error accepting connection from client {client_id}: {e}")
            raise
            
    async def handle_message(self, client_id: str, message: Dict) -> None:
        """Handle incoming WebSocket message."""
        try:
            message_type = message.get("type")
            if message_type == "sync_request":
                sync_data = await self._get_sync_data()
                await self.manager.broadcast_update(sync_data)
            else:
                logger.warning(f"Unknown message type: {message_type}")
        except Exception as e:
            logger.error(f"Error processing message from client {client_id}: {e}")
            
    async def disconnect(self, client_id: str) -> None:
        """Handle client disconnection."""
        await self.manager.unregister_client(client_id)
        logger.info(f"Client {client_id} disconnected")
        
    async def _get_sync_data(self) -> Dict:
        """Get latest blacklist and job history data for sync."""
        try:
            # Get blacklisted companies
            blacklisted = await self.blacklist.get_all_companies()
            
            # Get recent job history (last 30 days)
            history = await self.job_history.search_jobs(days=30)
            
            # Use DataClassJSONEncoder to properly handle dataclasses and enums
            data = {
                "blacklist": blacklisted,
                "history": history
            }
            
            # Convert to JSON and back to get a fully serializable dictionary
            return json.loads(
                json.dumps(data, cls=DataClassJSONEncoder)
            )
            
        except Exception as e:
            logger.error(f"Error getting sync data: {e}")
            return {"blacklist": [], "history": []} 