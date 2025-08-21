import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from fastapi import status, FastAPI
from unittest.mock import AsyncMock, patch, MagicMock

from config.global_constants import STORAGE_SETTINGS
from modules.api.rest.application_endpoints import ApplicationEndpoints
from modules.business.application.application_service import ApplicationService
from modules.models.services import ApplyType
from modules.business.cache.job_cache_service import JobCacheService
from modules.storage.job_history_storage import JobHistoryStorage
from modules.editor.manager import EditorManager

@pytest.fixture
def temp_job_history_file():
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_path = temp_file.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)

@pytest.fixture
def job_history(temp_job_history_file):
    with patch('Auto_job_applier_linkedIn.modules.storage.job_history_storage.STORAGE_SETTINGS', 
              {'history_file': temp_job_history_file}):
        return JobHistoryStorage()

@pytest.fixture
def job_cache():
    return JobCacheService()

@pytest.fixture
def mock_application_service():
    service = MagicMock(spec=ApplicationService)
    service.handle_apply = AsyncMock()
    service.finalize_application = AsyncMock()
    service.start_cover_letter_phase = AsyncMock()
    return service

@pytest.fixture
def application_service(job_cache, job_history):
    return ApplicationService(
        job_cache=job_cache,
        job_history=job_history
    )

@pytest.fixture
def application_endpoints(mock_application_service):
    return ApplicationEndpoints(mock_application_service)

@pytest.fixture
def test_client(application_endpoints):
    app = FastAPI()
    app.include_router(application_endpoints.router)
    return TestClient(app)

@pytest.mark.asyncio
async def test_apply_for_job(test_client, mock_application_service):
    # Setup
    job_id = "test-job"
    apply_type = ApplyType.EASY  # Use enum value
    mock_application_service.handle_apply.return_value = {
        "session_id": "test-session",
        "editor_url": "/editor?session=test-session"
    }
    
    # Test
    response = test_client.post(
        f"/api/apply/{job_id}",
        json={"apply_type": apply_type.value}  # Send as JSON body
    )
    
    # Verify
    assert response.status_code == status.HTTP_200_OK
    assert "session_id" in response.json()
    assert "editor_url" in response.json()
    mock_application_service.handle_apply.assert_called_once_with(job_id, apply_type)

@pytest.mark.asyncio
async def test_finalize_application(test_client, mock_application_service):
    # Setup
    session_id = "test-session"
    content = "test content"
    
    # Test
    response = test_client.post("/api/editor/finalize", json={"session_id": session_id, "content": content})
    
    # Verify
    assert response.status_code == status.HTTP_204_NO_CONTENT
    # Not implemented yet
    # mock_application_service.finalize_application.assert_called_once_with(session_id, content)

@pytest.mark.asyncio
async def test_handle_cover_letter_phase(test_client, mock_application_service):
    # Setup
    session_id = "test-session"
    mock_application_service.start_cover_letter_phase.return_value = {
        "session_id": session_id
    }
    
    # Test
    response = test_client.post(f"/api/apply/cover-letter/{session_id}")
    
    # Verify
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert "session_id" in response.json()
    mock_application_service.start_cover_letter_phase.assert_called_once_with(session_id) 