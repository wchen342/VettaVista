from fastapi import APIRouter

from vettavista_backend.modules.api.rest.application_endpoints import ApplicationEndpoints
from vettavista_backend.modules.api.rest.blacklist_endpoints import BlacklistEndpoints
from vettavista_backend.modules.api.rest.filter_endpoints import FilterEndpoints
from vettavista_backend.modules.api.rest.job_history_endpoints import JobHistoryEndpoints
from vettavista_backend.modules.business.application.application_service import ApplicationService
from vettavista_backend.modules.business.filter import PreliminaryFilterService, DetailedFilterService
from vettavista_backend.modules.storage.blacklist_storage import BlacklistStorage
from vettavista_backend.modules.storage.job_history_storage import JobHistoryStorage
from vettavista_backend.modules.sync.base import DataBroadcaster


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