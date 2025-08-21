from abc import ABC, abstractmethod
from typing import Dict, Optional
from fastapi import WebSocket

class WebSocketEndpoint(ABC):
    """Base class for WebSocket endpoints."""
    
    @abstractmethod
    async def handle_connection(self, websocket: WebSocket, client_id: str) -> None:
        """Handle new WebSocket connection."""
        pass
        
    @abstractmethod
    async def handle_message(self, client_id: str, message: Dict) -> None:
        """Handle incoming WebSocket message."""
        pass
        
    @abstractmethod
    async def disconnect(self, client_id: str) -> None:
        """Handle client disconnection."""
        pass
