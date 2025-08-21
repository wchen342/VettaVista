import os
import shutil
import asyncio
from pathlib import Path

import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Type, TypeVar
import logging
from vettavista_backend.modules.storage.base import StorageService
from dataclasses import fields

logger = logging.getLogger(__name__)

T = TypeVar('T')

class CSVStorageService(StorageService):
    """Base class for CSV-based storage models"""
    
    def __init__(self, file_path: str, key_column: str, data_class: Type[T], backup_enabled: bool = False):
        """Initialize CSV storage
        
        Args:
            file_path: Path to CSV file
            key_column: Name of the column to use as primary key
            data_class: Dataclass type representing the data
            backup_enabled: Whether to enable periodic backups
        """
        self.file_path = Path(file_path)
        self.key_column = key_column
        self.columns = [f.name for f in fields(data_class)]
        self._backup_task = None
        self._backup_enabled = backup_enabled
        self._ensure_file_exists()
        
    def _ensure_file_exists(self):
        """Create file if it doesn't exist"""
        self.file_path.parent.mkdir(exist_ok=True)
        if not os.path.exists(self.file_path):
            df = pd.DataFrame(columns=self.columns)
            df.to_csv(self.file_path, index=False)
            logger.info(f"Created new CSV file: {self.file_path}")
            
    def _read_df(self) -> pd.DataFrame:
        """Read CSV file into DataFrame. All columns are read as strings."""
        try:
            # Read CSV with string type for all columns except specific numeric ones
            df = pd.read_csv(
                self.file_path,
                dtype={col: str for col in self.columns},  # Force string type for all columns
                na_values=['nan', 'NaN', 'NAN', ''],  # Define what should be considered as NA
                keep_default_na=False  # Don't use default NA values
            )
            # Replace NaN values with empty string
            df = df.fillna('')
            return df
        except Exception as e:
            logger.error(f"Error reading CSV file: {e}")
            return pd.DataFrame(columns=self.columns)
            
    def _write_df(self, df: pd.DataFrame):
        """Write DataFrame to CSV file"""
        try:
            df.to_csv(self.file_path, index=False)
        except Exception as e:
            logger.error(f"Error writing to CSV file: {e}")
            
    async def start_backup_scheduler(self, interval: int = 3600):
        """Start the backup scheduler
        
        Args:
            interval: Backup interval in seconds (default: 1 hour)
        """
        if not self._backup_enabled:
            logger.info("Backup not enabled for this storage")
            return
            
        if self._backup_task is None:
            self._backup_task = asyncio.create_task(self._backup_periodically(interval))
            logger.info(f"Started backup scheduler for {self.file_path}")
        
    def stop_backup_scheduler(self):
        """Stop the backup scheduler"""
        if self._backup_task is not None:
            self._backup_task.cancel()
            self._backup_task = None
            logger.info(f"Stopped backup scheduler for {self.file_path}")
            
    async def _backup_periodically(self, interval: int):
        """Periodically backup the file
        
        Args:
            interval: Backup interval in seconds
        """
        while True:
            try:
                self._create_backup()
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Failed to create backup: {e}")
                await asyncio.sleep(3600)  # Retry in an hour
                
    def _create_backup(self):
        """Create a backup of the file"""
        file_path = Path(self.file_path)

        if not file_path.exists():
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{self.file_path}.{timestamp}.bak"
        shutil.copy2(self.file_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        
        # Keep only last 2 backups
        # Get the directory and filename separately
        parent_dir = file_path.parent
        file_name = file_path.name

        # Find all backups of this specific file in its directory
        backups = sorted(parent_dir.glob(f"{file_name}.*.bak"))

        # Remove old backups (keep the 2 most recent)
        for old_backup in backups[:-2]:
            old_backup.unlink()
            logger.info(f"Removed old backup: {old_backup}")
            
    async def get(self, key: str) -> Optional[Dict]:
        """Get a single row by key"""
        df = self._read_df()
        row = df[df[self.key_column] == key]
        if len(row) == 0:
            return None
        return row.iloc[0].to_dict()
        
    async def set(self, key: str, value: Dict) -> None:
        """Set a single row"""
        df = self._read_df()
        value[self.key_column] = key
        value['date_updated'] = datetime.now().isoformat()
        
        # Find exact matches using equality comparison
        mask = (df[self.key_column] == key)  # This ensures exact matching
        
        # Update existing or append new
        if mask.any():  # Check if we found any exact matches
            row_idx = df.index[mask][0]
            for col, val in value.items():
                if col in df.columns:
                    df.at[row_idx, col] = val
        else:
            value['date_created'] = value.get('date_created', value['date_updated'])
            df = pd.concat([df, pd.DataFrame([value])], ignore_index=True)
            
        self._write_df(df)
        
    async def delete(self, key: str) -> None:
        """Delete a single row"""
        df = self._read_df()
        df = df[df[self.key_column] != key]
        self._write_df(df)
        
    async def query(self, filter_params: Dict = None) -> List[Dict]:
        """Query rows with optional filters"""
        df = self._read_df()
        
        if filter_params:
            for col, value in filter_params.items():
                if col in df.columns:
                    df = df[df[col] == value]
                    
        return df.to_dict('records')
        
    async def get_all(self) -> List[Dict]:
        """Get all rows"""
        df = self._read_df()
        return df.to_dict('records') 