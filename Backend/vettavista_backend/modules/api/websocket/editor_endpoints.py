import logging
from typing import Dict, Any
from fastapi import WebSocket, APIRouter
import json
from fastapi.websockets import WebSocketState
from starlette.websockets import WebSocketDisconnect

from vettavista_backend.modules.api.websocket.base import WebSocketEndpoint
from vettavista_backend.modules.editor.manager import EditorManager
from vettavista_backend.modules.editor.types import ServerMessage, MessageType, PhaseData, EditorUpdate
from vettavista_backend.modules.utils import DataClassJSONEncoder

logger = logging.getLogger(__name__)

class EditorEndpoints(WebSocketEndpoint):
    def __init__(self, editor_manager: EditorManager):
        self.editor_manager = editor_manager
        self.router = APIRouter()
        self.setup_routes()

    def setup_routes(self):
        """Setup routes for editor endpoints"""
        @self.router.websocket("/ws/editor/{session_id}")
        async def websocket_endpoint(websocket: WebSocket, session_id: str):
            await self.handle_connection(websocket, session_id)
            
            try:
                while True:
                    data = await websocket.receive_json()
                    await self.handle_message(session_id, data)
            except WebSocketDisconnect:
                await self.editor_manager.unregister_client(session_id)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if websocket.client_state != WebSocketState.DISCONNECTED:
                    await websocket.close(code=1000)
                await self.editor_manager.unregister_client(session_id)

    async def _send_error(self, client_id: str, error_message: str) -> None:
        """Helper method to send error messages to client"""
        logger.error(f"Error for client {client_id}: {error_message}")
        websocket = self.editor_manager.active_connections.get(client_id)
        if websocket is not None:   # needed for testing mocks
            await websocket.send_text(json.dumps(ServerMessage(
                type=MessageType.ERROR,
                error_message=error_message
            ), cls=DataClassJSONEncoder))

    async def handle_connection(self, websocket: WebSocket, session_id: str) -> None:
        """Handle incoming WebSocket connection"""
        logger.info(f"Attempting to connect editor session {session_id}")
        
        # Get session before accepting connection
        task = self.editor_manager.get_task_by_session_id(session_id)
        if not task:
            logger.error(f"Invalid session ID: {session_id}")
            await websocket.close(code=4000, reason="Invalid session ID")
            return

        try:
            # Register client and accept connection
            await self.editor_manager.register_client(session_id, websocket)

            # Send initial state
            await websocket.send_text(json.dumps(ServerMessage(
                type=MessageType.INIT,
                phase_data=PhaseData(
                    original=task.resume_data.original,
                    customized=task.resume_data.customized,
                    recommended_skills=task.recommended_skills
                )
            ), cls=DataClassJSONEncoder))
            logger.info(f"Sent initial data to session {session_id}")

        except Exception as e:
            logger.error(f"WebSocket error in session {session_id}: {e}")
            await websocket.close(code=4000, reason=str(e))
            await self.editor_manager.unregister_client(session_id)

    async def handle_message(self, session_id: str, message: Dict) -> None:
        """Handle incoming WebSocket message."""
        try:
            logger.info(f"Received message from session {session_id}: {message}")
            
            # Handle message based on type
            response = await self.editor_manager.handle_update(EditorUpdate(
                session_id=session_id,
                new_value=message['new_value']
            ))
            if not response.success:
                await self._send_error(session_id, response.error_message)
                
        except json.JSONDecodeError as e:
            await self._send_error(session_id, "Invalid JSON data")
        except Exception as e:
            await self._send_error(session_id, str(e))

    async def disconnect(self, client_id: str) -> None:
        """Handle client disconnection."""
        await self.editor_manager.unregister_client(client_id)
        logger.info(f"Client {client_id} disconnected")
