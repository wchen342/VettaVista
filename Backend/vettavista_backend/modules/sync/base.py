from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Protocol
from fastapi import WebSocket

class SyncManager(ABC):
    """Base interface for sync operations."""
    
    @abstractmethod
    async def register_client(self, client_id: str, websocket: WebSocket) -> None:
        """Register a new client connection."""
        pass
        
    @abstractmethod
    async def unregister_client(self, client_id: str) -> None:
        """Unregister a client connection."""
        pass
        
    @abstractmethod
    async def broadcast_update(self, data: Dict) -> None:
        """Broadcast an update to all connected clients."""
        pass
        
    @abstractmethod
    async def get_client_state(self, client_id: str) -> Dict:
        """Get the current state for a client."""
        pass
        
    @abstractmethod
    async def handle_client_message(self, client_id: str, message: Dict) -> None:
        """Handle an incoming message from a client."""
        pass 

class DataBroadcaster(Protocol):
    """Interface for broadcasting data updates"""
    async def broadcast_update(self, data: Dict) -> None:
        """Broadcast an update to all listeners"""
        pass

class NoOpBroadcaster(DataBroadcaster):
    """Default broadcaster that does nothing"""
    async def broadcast_update(self, data: Dict) -> None:
        pass 