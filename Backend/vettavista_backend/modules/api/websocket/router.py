import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from vettavista_backend.modules.api.websocket.sync_endpoints import SyncEndpoints
from vettavista_backend.modules.api.websocket.editor_endpoints import EditorEndpoints
from vettavista_backend.modules.editor.manager import EditorManager

logger = logging.getLogger(__name__)

def create_router(editor_manager: EditorManager) -> APIRouter:
    router = APIRouter()

    # Initialize endpoints
    sync_endpoints = SyncEndpoints()
    editor_endpoints = EditorEndpoints(editor_manager)

    # Include routers
    router.include_router(sync_endpoints.router)
    router.include_router(editor_endpoints.router)

    return router
