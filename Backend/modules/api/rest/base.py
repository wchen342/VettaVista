from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from fastapi import APIRouter

class BaseRESTEndpoint(ABC):
    """Base class for REST endpoints."""
    
    def __init__(self):
        self.router = APIRouter()
        self.setup_routes()
    
    @abstractmethod
    def setup_routes(self) -> None:
        """Setup routes for this endpoint group."""
        pass
    
    @property
    def routes(self) -> APIRouter:
        """Get the router with all routes."""
        return self.router 