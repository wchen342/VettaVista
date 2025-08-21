from fastapi import APIRouter
from modules.business.filter import PreliminaryFilterService, DetailedFilterService
from modules.business.application.application_service import ApplicationService
from modules.storage.blacklist_storage import BlacklistStorage
from modules.storage.job_history_storage import JobHistoryStorage
from modules.sync.base import DataBroadcaster
from modules.api.rest.filter_endpoints import FilterEndpoints
from modules.api.rest.blacklist_endpoints import BlacklistEndpoints
from modules.api.rest.job_history_endpoints import JobHistoryEndpoints
from modules.api.rest.application_endpoints import ApplicationEndpoints

def create_rest_api(
    preliminary_filter_service: PreliminaryFilterService,
    detailed_filter_service: DetailedFilterService,
    blacklist_storage: BlacklistStorage,
    job_history_storage: JobHistoryStorage,
    broadcaster: DataBroadcaster,
    application_service: ApplicationService
) -> APIRouter:
    """Create and configure the REST API router."""
    api_router = APIRouter()
    
    # Initialize endpoints
    filter_endpoints = FilterEndpoints(preliminary_filter_service, detailed_filter_service)
    blacklist_endpoints = BlacklistEndpoints(blacklist_storage, broadcaster)
    job_history_endpoints = JobHistoryEndpoints(job_history_storage, broadcaster)
    application_endpoints = ApplicationEndpoints(application_service)
    
    # Include all routes
    api_router.include_router(filter_endpoints.routes)
    api_router.include_router(blacklist_endpoints.routes)
    api_router.include_router(job_history_endpoints.routes)
    api_router.include_router(application_endpoints.routes)
    
    return api_router 