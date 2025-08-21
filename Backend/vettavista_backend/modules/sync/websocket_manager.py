import logging
from typing import Dict, Optional
from fastapi import WebSocket, WebSocketDisconnect
from vettavista_backend.modules.sync.base import SyncManager, DataBroadcaster
from vettavista_backend.modules.storage import BlacklistStorage, JobHistoryStorage
from vettavista_backend.modules.utils import DataClassJSONEncoder
import json

logger = logging.getLogger(__name__)

class WebSocketSyncManager(SyncManager, DataBroadcaster):
    def __init__(self, blacklist_storage: BlacklistStorage, job_history_storage: JobHistoryStorage):
        """Initialize the WebSocket sync manager."""
        self.active_connections: Dict[str, WebSocket] = {}
        self.blacklist_storage = blacklist_storage
        self.job_history_storage = job_history_storage
        
    async def register_client(self, client_id: str, websocket: WebSocket) -> None:
        """Register a new client connection."""
        try:
            await websocket.accept()
            self.active_connections[client_id] = websocket
            logger.info(f"Client {client_id} connected successfully")
            
            # Send initial state through broadcast
            state = await self.get_client_state(client_id)
            await self.broadcast_update(state)
        except Exception as e:
            logger.error(f"Error accepting connection from client {client_id}: {e}")
            raise
            
    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        """Connect and register a new client."""
        await self.register_client(client_id, websocket)

    async def unregister_client(self, client_id: str) -> None:
        """Unregister a client connection."""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} disconnected and removed from active connections")
            
    async def broadcast_update(self, data: Dict) -> None:
        """Broadcast message to all connected clients."""
        message = {"type": "sync_response", "data": data}
        for client_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
                logger.info(f"Update broadcast to client {client_id}")
            except Exception as e:
                logger.error(f"Error broadcasting to client {client_id}: {e}")
                # Don't raise here to continue broadcasting to other clients
                
    async def get_client_state(self, client_id: str) -> Dict:
        """Get the current state for a client."""
        try:
            # Get blacklist and recent job history using specific methods
            blacklist = await self.blacklist_storage.get_all_companies()
            history = await self.job_history_storage.search_jobs(days=30)
            
            # Create response data
            data = {
                "blacklist": blacklist,
                "history": history
            }
            
            # Convert to JSON-serializable format and validate
            try:
                json_data = json.loads(
                    json.dumps(data, cls=DataClassJSONEncoder)
                )
                logger.info(f"Prepared sync data: {json_data}")
                return json_data
            except Exception as e:
                logger.error(f"JSON serialization error: {e}")
                # Return empty lists as fallback
                return {
                    "blacklist": [],
                    "history": []
                }
            
        except Exception as e:
            logger.error(f"Error getting state for client {client_id}: {e}")
            raise
            
    async def handle_client_message(self, client_id: str, message: Dict) -> None:
        """Handle an incoming message from a client."""
        try:
            message_type = message.get("type")
            if message_type == "sync_request":
                state = await self.get_client_state(client_id)
                await self.broadcast_update(state)
            else:
                logger.warning(f"Unknown message type from client {client_id}: {message_type}")
                
        except Exception as e:
            logger.error(f"Error handling message from client {client_id}: {e}")
            raise 