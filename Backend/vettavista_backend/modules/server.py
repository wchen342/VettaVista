import logging
import os
import traceback
from contextlib import asynccontextmanager
from functools import wraps
from importlib import resources
from importlib.resources import as_file
from typing import Callable

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Add project root to Python path
# project_root = str(Path(__file__).resolve().parent.parent)
# if project_root not in sys.path:
#     sys.path.insert(0, project_root)
#     logger.info(f"Added {project_root} to Python path")

from vettavista_backend.modules.sync import WebSocketSyncManager
from vettavista_backend.modules.business.utils.skill_matcher import SimpleSkillMatcher
from vettavista_backend.modules.business.utils.title_matcher import AdvancedEmbeddingMatcher
from vettavista_backend.modules.api.websocket import create_router
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from fastapi.staticfiles import StaticFiles

# Import configurations using the new system
from vettavista_backend.config import search

# Now import project modules
from vettavista_backend.modules.storage.blacklist_storage import BlacklistStorage
from vettavista_backend.modules.storage.job_history_storage import JobHistoryStorage
from vettavista_backend.modules.business.filter import PreliminaryFilterService, DetailedFilterService
from vettavista_backend.modules.business.application.application_service import ApplicationService
from vettavista_backend.modules.business.cache.job_cache_service import JobCacheService
from vettavista_backend.modules.api.middleware import RequestLimitMiddleware
from vettavista_backend.modules.api.rest import create_rest_api
from vettavista_backend.modules.editor.manager import EditorManager

# TODO: needs proper dependency injection and lifecycle

# Initialize storage models
blacklist_storage = BlacklistStorage()
job_history_storage = JobHistoryStorage()

# Initialize shared matchers with typed configs
title_matcher = AdvancedEmbeddingMatcher(search.preferred_titles)
skill_matcher = SimpleSkillMatcher()

# Initialize cache service
job_cache_service = JobCacheService()

# Initialize services with shared matchers
preliminary_filter_service = PreliminaryFilterService(
    blacklist_storage=blacklist_storage,
    job_history_storage=job_history_storage,
    title_matcher=title_matcher,
    job_cache=job_cache_service
)
detailed_filter_service = DetailedFilterService(
    blacklist_storage=blacklist_storage, 
    job_history_storage=job_history_storage,
    title_matcher=title_matcher,
    skill_matcher=skill_matcher,
    job_cache=job_cache_service
)

# Create editor manager with job cache
editor_manager = EditorManager(
    active_tasks={},
    job_cache=job_cache_service
)

# Create WebSocket sync manager (implements DataBroadcaster)
websocket_sync_manager = WebSocketSyncManager(blacklist_storage=blacklist_storage, job_history_storage=job_history_storage)

# Initialize application service with editor manager and broadcaster
application_service = ApplicationService(
    job_cache=job_cache_service,
    job_history=job_history_storage,
    editor_manager=editor_manager,
    broadcaster=websocket_sync_manager  # Add broadcaster
)

# Create REST API router with the WebSocket sync manager as the broadcaster
rest_api_router = create_rest_api(
    preliminary_filter_service=preliminary_filter_service,
    detailed_filter_service=detailed_filter_service,
    blacklist_storage=blacklist_storage,
    job_history_storage=job_history_storage,
    broadcaster=websocket_sync_manager,
    application_service=application_service
)

# Create WebSocket router with shared editor manager
websocket_router = create_router(editor_manager)

# Define regex pattern for experience extraction
re_experience = r'(\d+)(?:\+|\s*-\s*\d+)?\s*(?:years?|yrs?)'

def handle_endpoint_errors(func: Callable):
    """Decorator to handle common error patterns in HTTP endpoints"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
            # Return empty dict for None responses
            if result is None:
                return {}
            return result
        except HTTPException:
            # Re-raise HTTP exceptions as they're already properly formatted
            raise
        except (KeyError, ValueError) as e:
            # Handle missing required fields and validation errors as 400
            logger.error(str(e))
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            logger.error(f"Error details: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))
    return wrapper

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    # Startup
    logger.info("Starting server...")
    await preliminary_filter_service.clear_cache()  # Clear cache on startup
    await detailed_filter_service.clear_cache()  # Clear cache on startup
    await job_history_storage.start_backup_scheduler()
    await blacklist_storage.start_backup_scheduler()
    yield
    # Shutdown
    logger.info("Shutting down server...")
    job_history_storage.stop_backup_scheduler()
    blacklist_storage.stop_backup_scheduler()

# Initialize FastAPI with lifespan
app = FastAPI(lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for editor
# with resources.path("vettavista_backend", "static") as static_path:
#     static_path
static_path = resources.files("vettavista_backend.static").joinpath("editor").absolute()
app.mount("/editor", StaticFiles(directory=static_path, html=True), name="editor")

# Add request limiting middleware
app.add_middleware(RequestLimitMiddleware)

# Include routers
app.include_router(websocket_router, prefix="")  # No prefix to maintain compatibility with extension
app.include_router(rest_api_router)


def main():
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()