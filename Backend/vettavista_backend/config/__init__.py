"""Configuration management for the application.

This module handles loading configuration from template files and local overrides.
Template files provide default values, while local files (if they exist) override these defaults.

Directory Structure:
    config/
        templates/  - Template files with default values (.yaml)
    {user_data_dir}/local/     - Local override files (OS-dependent)
"""
import logging
import os
import shutil
from dataclasses import is_dataclass, fields, dataclass
from datetime import datetime
from importlib import resources
from pathlib import Path
from threading import Lock
from typing import Dict, Any, Type, List, Generic, TypeVar, Callable

import platformdirs
import yaml
from watchdog.events import FileSystemEventHandler, FileSystemEvent, DirMovedEvent, \
    FileMovedEvent, DirModifiedEvent, FileModifiedEvent, DirCreatedEvent, FileCreatedEvent
from watchdog.observers import Observer

from vettavista_backend.config.global_constants import VERSION, APP_NAME
from vettavista_backend.config.models import (
    PersonalsModel, ResumeModel, SecretsModel,
    ExperienceEntry, ProjectEntry, Education, SearchModel, AISettingModel, AIPromptsModel
)

T = TypeVar('T')

logger = logging.getLogger(__name__)

def convert_datetime(value: str) -> datetime:
    """Convert YAML datetime string to datetime object."""
    if value == "Present":
        return datetime.max
    return datetime.strptime(value, "%Y-%m")

def construct_nested_objects(data: Dict[str, Any], model_class: Type) -> Dict[str, Any]:
    """Recursively construct nested dataclass objects."""
    if not is_dataclass(model_class):
        return data

    field_types = {f.name: f.type for f in fields(model_class)}
    result = {}

    for key, value in data.items():
        if key not in field_types:
            continue

        field_type = field_types[key]
        
        # Handle datetime fields
        if field_type == datetime and isinstance(value, str):
            result[key] = convert_datetime(value)
            continue

        # Handle lists of dataclass objects
        if getattr(field_type, "__origin__", None) == list:
            item_type = field_type.__args__[0]
            if is_dataclass(item_type) and isinstance(value, list):
                result[key] = [
                    item_type(**construct_nested_objects(item, item_type))
                    for item in value
                ]
                continue

        # Handle nested dataclass
        if is_dataclass(field_type) and isinstance(value, dict):
            result[key] = field_type(**construct_nested_objects(value, field_type))
            continue

        result[key] = value

    return result

class ConfigFileHandler(FileSystemEventHandler):
    """Handles file system events for config files."""
    def __init__(self, refresh_callback: Callable):
        super().__init__()
        self.watched_filenames = set()
        self.refresh_callback = refresh_callback

    def add_watched_file(self, filepath):
        """Add a file's basename to the watch list."""
        self.watched_filenames.add(filepath)

    def on_created(self, event: DirCreatedEvent | FileCreatedEvent) -> None:
        self._on_filtered_event(event)

    def on_modified(self, event: DirModifiedEvent | FileModifiedEvent) -> None:
        self._on_filtered_event(event)

    def _on_filtered_event(self, event: FileSystemEvent) -> None:
        # Watch for any event affecting our target files
        if event.src_path in self.watched_filenames:
            self.refresh_callback()
            return

        # Check if it's a directory and search recursively
        if os.path.isdir(event.src_path):
            for root, _, files in os.walk(event.src_path):
                if any(os.path.join(root, filename) in self.watched_filenames for filename in files):
                    self.refresh_callback()
                    return

    def on_moved(self, event: DirMovedEvent | FileMovedEvent) -> None:
        if event.dest_path in self.watched_filenames:
            self.refresh_callback()
            return

        # Check if it's a directory and search recursively
        if os.path.isdir(event.dest_path):
            for root, _, files in os.walk(event.dest_path):
                if any(os.path.join(root, filename) in self.watched_filenames for filename in files):
                    self.refresh_callback()
                    return

@dataclass
class ConfigState(Generic[T]):
    data: T

class DynamicConfig(Generic[T]):
    def __init__(self, name: str, model_class: type[T]):
        self.name = name
        self.model_class = model_class
        self.template_path = resources.files('vettavista_backend.config.templates').joinpath(f"{name}.yaml")

        # Set up platform-specific config directory using platformdirs
        config_dir = Path(platformdirs.user_config_dir(APP_NAME, appauthor=False, version=VERSION))
        local_dir = config_dir / "local"

        # Create config and local directories if they don't exist
        local_dir.mkdir(parents=True, exist_ok=True)

        self.local_path = str(local_dir / f"{name}.yaml")

        # Copy template to local if local doesn't exist but template does
        if os.path.exists(str(self.template_path)) and not os.path.exists(self.local_path):
            shutil.copy2(str(self.template_path), self.local_path)

        self._state: ConfigState[T] | None = None
        self._lock = Lock()

        self._load_config()

        # List to store callback functions from other classes
        self._listeners: List[Callable[[T], None]] = []

        # Setup file watching
        self._file_handler = ConfigFileHandler(self.refresh)
        self._file_handler.add_watched_file(str(self.template_path))
        self._file_handler.add_watched_file(os.path.realpath(self.local_path))

        self._observer = Observer()

        # Watch both template and local directories
        template_dir = os.path.dirname(str(self.template_path))
        self._observer.schedule(self._file_handler, template_dir, recursive=False)
        self._observer.schedule(self._file_handler, str(self.template_path), recursive=False)
        self._observer.schedule(self._file_handler, str(os.path.realpath(local_dir)), recursive=True)
        self._observer.schedule(self._file_handler, str(os.path.realpath(self.local_path)), recursive=True)

        self._observer.start()

    def register_listener(self, callback: Callable[[T], None]) -> None:
        """
        Register a callback function to be called when config changes.
        The callback will receive the updated config object.

        Args:
            callback: A function that takes the config object as its argument
        """
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[T], None]) -> None:
        """
        Remove a previously registered callback function.

        Args:
            callback: The callback function to remove
        """
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify_listeners(self, config: T) -> None:
        """Notify all registered listeners with the current config."""
        for listener in self._listeners:
            try:
                listener(config)
            except Exception as e:
                # Handle or log errors from listeners
                logging.error(f"Error in config listener: {e}")

    def _load_config(self) -> None:
        config = {}

        # Load from template
        if os.path.exists(str(self.template_path)):
            with self.template_path.open('r') as f:
                template_data = yaml.safe_load(f)
                config.update(template_data or {})

        # Load from platform-specific local path
        if os.path.exists(self.local_path):
            with open(self.local_path, "r") as f:
                local_data = yaml.safe_load(f)
                config.update(local_data or {})

        processed_config = construct_nested_objects(config, self.model_class)
        self._state = ConfigState(
            data=self.model_class(**processed_config)
        )

    def get(self) -> T:
        return self._state.data

    def refresh(self):
        with self._lock:
            self._load_config()
            config = self._state.data

        # Notify listeners outside the lock to avoid deadlocks
        if self._listeners:
            self._notify_listeners(config)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.get(), name)

    def __del__(self):
        """Clean up the observer when the config object is destroyed."""
        self._observer.stop()
        self._observer.join()

# Initialize dynamic configurations
personals = DynamicConfig('personals', PersonalsModel)
resume = DynamicConfig('resume', ResumeModel)
search = DynamicConfig('search', SearchModel)
secrets = DynamicConfig('secrets', SecretsModel)
ai_settings = DynamicConfig('ai_settings', AISettingModel)
ai_prompts = DynamicConfig('ai_prompts', AIPromptsModel)