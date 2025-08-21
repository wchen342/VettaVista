from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import pandas as pd

class StorageService(ABC):
    """Base interface for all storage models"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Dict]:
        """Get a single item by key"""
        pass
        
    @abstractmethod
    async def set(self, key: str, value: Dict) -> None:
        """Set a single item"""
        pass
        
    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a single item"""
        pass
        
    @abstractmethod
    async def query(self, filter_params: Dict = None) -> List[Dict]:
        """Query items with optional filters"""
        pass
        
    @abstractmethod
    async def get_all(self) -> List[Dict]:
        """Get all items"""
        pass 