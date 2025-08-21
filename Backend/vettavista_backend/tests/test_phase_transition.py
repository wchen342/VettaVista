import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock, create_autospec
import asyncio
import async_timeout

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from config import resume
from config.global_constants import STORAGE_SETTINGS
from modules.api.rest.application_endpoints import ApplicationEndpoints
from modules.business.application.application_service import ApplicationService
from modules.business.cache.job_cache_service import JobCacheService
from modules.editor.manager import EditorManager
from modules.editor.types import MessageType, PhaseData
from modules.storage.job_history_storage import JobHistoryStorage
from modules.ai.protocols import ClaudeServiceProtocol
from modules.models.services import JobDetailedInfo, ApplicationPhase, ProcessingStatus, GlassdoorRating
from tests.conftest import create_test_resume
from modules.api.websocket.editor_endpoints import EditorEndpoints

# Test data
DUMMY_ORIGINAL_LATEX = "\\documentclass{article}\n\\begin{document}\nOriginal Resume\n\\end{document}"
DUMMY_CUSTOMIZED_LATEX = "\\documentclass{article}\n\\begin{document}\nCustomized Resume\n\\end{document}"
DUMMY_COVER_LETTER_BODY = "This is a test cover letter."
DUMMY_COVER_LETTER = "Dear Hiring Team at Test Company,\n\nThis is a test cover letter.\n\nSincerely,"

# Add test data for job info
DUMMY_JOB_INFO = JobDetailedInfo(
    jobId="test-job-123",
    title="Software Engineer",
    company="Test Company",
    location="Test Location",
    description="This is a test job description requiring Python and FastAPI experience.",
    url="https://linkedin.com/jobs/test-job-123",
    glassdoorRating=GlassdoorRating(rating=3., reviewCount=10, isValid=False)
)

@pytest.fixture
def temp_job_history_file():
    """Create a temporary file for job history storage."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_path = temp_file.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)

@pytest.fixture
def job_cache():
    """Create JobCacheService instance."""
    return JobCacheService()

@pytest.fixture
def job_history(temp_job_history_file):
    """Create JobHistoryStorage with temporary file."""
    with patch('modules.storage.job_history_storage.STORAGE_SETTINGS', 
              {'history_file': temp_job_history_file}):
        return JobHistoryStorage()

@pytest.fixture
def active_tasks():
    """Shared dictionary of active tasks between services."""
    return {}

@pytest.fixture
def mock_broadcaster():
    # Create a basic mock object
    mock = MagicMock()
    # Attach an AsyncMock for the async method
    mock.broadcast_update = AsyncMock()
    return mock

@pytest.fixture
def editor_manager(active_tasks, job_cache):
    """Create shared EditorManager instance."""
    return EditorManager(active_tasks=active_tasks, job_cache=job_cache)

@pytest.fixture
def mock_claude_service():
    """Create a mock Claude service."""
    mock_service = create_autospec(ClaudeServiceProtocol)
    
    # Create test resumes using the helper
    original_resume = create_test_resume()
    customized_resume = create_test_resume(
        skills={
            'Programming Languages': ['Python', 'JavaScript', 'TypeScript'],
            'Frameworks': ['FastAPI', 'React', 'Django'],
            'Tools': ['Git', 'Docker', 'AWS']
        }
    )
    
    # Create async mock functions
    mock_customize_resume = AsyncMock(return_value=(original_resume, customized_resume))
    mock_customize_cover_letter = AsyncMock(return_value=DUMMY_COVER_LETTER_BODY)
    
    # Assign the async mocks
    mock_service.customize_resume = mock_customize_resume
    mock_service.customize_cover_letter = mock_customize_cover_letter
    return mock_service

@pytest.fixture
def application_service(job_cache, job_history, editor_manager, mock_broadcaster, mock_claude_service):
    """Create ApplicationService with dependencies."""
    service = ApplicationService(
        job_cache=job_cache,
        job_history=job_history,
        editor_manager=editor_manager,
        broadcaster=mock_broadcaster,
        claude_service=mock_claude_service
    )
    # Share the active_tasks dictionary
    service._active_tasks = editor_manager.active_tasks
    return service

@pytest.fixture
def editor_endpoints(editor_manager):
    """Create EditorEndpoints with WebSocket support."""
    return EditorEndpoints(editor_manager)

@pytest.fixture
def application_endpoints(application_service):
    """Create ApplicationEndpoints with service."""
    return ApplicationEndpoints(application_service)

@pytest.fixture
def app(application_endpoints, editor_endpoints):
    """Create FastAPI app with all routes."""
    app = FastAPI()
    app.include_router(application_endpoints.router)
    app.include_router(editor_endpoints.router)
    return app

@pytest.fixture
def test_client(app):
    """Create TestClient for REST endpoints."""
    return TestClient(app)

@pytest.mark.asyncio
async def test_initial_apply(test_client, application_service, job_cache):
    """Test the initial application flow including WebSocket initialization.
    
    Steps tested:
    1. POST to /api/apply/{job_id} with apply type
    2. Verify response contains session_id and editor_url
    3. Test WebSocket connection
    4. Verify INIT message content
    """
    # Setup cache first
    await job_cache.set_job_info(DUMMY_JOB_INFO.jobId, DUMMY_JOB_INFO)
    
    # Test apply endpoint
    job_id = DUMMY_JOB_INFO.jobId
    response = test_client.post(
        f"/api/apply/{job_id}",
        json={"apply_type": "easy_apply"}
    )
    assert response.status_code == 200
    
    data = response.json()
    session_id = data["session_id"]
    assert "editor_url" in data
    assert data["editor_url"] == f"/editor?session={session_id}"
    
    # Test WebSocket connection through FastAPI TestClient
    with test_client.websocket_connect(f"/ws/editor/{session_id}") as websocket:
        # Receive and verify INIT message
        init_message = json.loads(websocket.receive_text())
        assert init_message["type"] == MessageType.INIT
        assert isinstance(init_message["phase_data"], dict)
        assert "original" in init_message["phase_data"]
        assert "customized" in init_message["phase_data"]
        
        # Verify LaTeX content structure instead of exact match
        assert "\\documentclass" in init_message["phase_data"]["original"]
        assert "\\begin{document}" in init_message["phase_data"]["original"]
        assert "\\end{document}" in init_message["phase_data"]["original"]
        
        # Verify customized content has similar structure
        assert "\\documentclass" in init_message["phase_data"]["customized"]
        assert "\\begin{document}" in init_message["phase_data"]["customized"]
        assert "\\end{document}" in init_message["phase_data"]["customized"]
        
        # Verify the customized content includes skills from mock resume
        original_resume, customized_resume = application_service._claude.customize_resume.return_value
        for skill in customized_resume.skills.get('Programming Languages', []):
            assert skill in init_message["phase_data"]["customized"]

        # Small delay before sending update
        await asyncio.sleep(0.1)
        test_update = {
            "type": "update",
            "session_id": session_id,
            "new_value": "\\documentclass{article}\n\\begin{document}\nUpdated Resume Content\n\\end{document}"
        }
        websocket.send_json(test_update)
        
        # Wait for response with timeout
        try:
            async with async_timeout.timeout(2.0):
                update_response = json.loads(websocket.receive_text())
                assert update_response["type"] == MessageType.UPDATE
                assert isinstance(update_response["phase_data"], dict)
                assert "customized" in update_response["phase_data"]
                assert "preview_data" in update_response["phase_data"]  # PDF preview should be generated
                assert test_update["new_value"] == update_response["phase_data"]["customized"]
        except asyncio.TimeoutError:
            pytest.fail("Timeout waiting for WebSocket response")

@pytest.mark.asyncio
async def test_phase_transition(test_client, application_service, job_cache):
    """Test transition from resume to cover letter phase."""
    # Setup cache first
    await job_cache.set_job_info(DUMMY_JOB_INFO.jobId, DUMMY_JOB_INFO)
    
    # Setup mock Claude service to return proper resume data
    mock_resume = create_test_resume()
    application_service._claude.customize_resume.return_value = (mock_resume, mock_resume)
    application_service._claude.customize_cover_letter.return_value = DUMMY_COVER_LETTER_BODY
    
    # Mock PDF generation and preview conversion
    application_service._editor_manager.cover_letter_generator.generate_pdf_from_latex = MagicMock(return_value="mock.pdf")
    application_service._editor_manager._convert_pdf_to_preview = MagicMock(return_value="mock_preview_data")
    
    # Test apply endpoint
    job_id = DUMMY_JOB_INFO.jobId
    response = test_client.post(
        f"/api/apply/{job_id}",
        json={"apply_type": "easy_apply"}
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    
    # Wait for task to be ready
    task = application_service._active_tasks[session_id]
    while task.status == ProcessingStatus.PROCESSING:
        await asyncio.sleep(0.1)
    
    with test_client.websocket_connect(f"/ws/editor/{session_id}") as websocket:
        # Clear initial INIT message
        init_message = json.loads(websocket.receive_text())
        assert init_message["type"] == MessageType.INIT
        print(f"Received INIT message: {init_message}")
        
        # Test phase transition
        print("Sending phase transition request")
        response = test_client.post(f"/api/apply/cover-letter/{session_id}")
        assert response.status_code == 202
        print(f"Phase transition response: {response.status_code}")

        # Get phase change message
        print("Waiting for phase change message")
        phase_message = json.loads(websocket.receive_text())
        print(f"Received phase message: {phase_message}")
        assert phase_message["type"] == MessageType.PHASE_CHANGE
        assert phase_message["phase"] == ApplicationPhase.COVER_LETTER.value
        assert isinstance(phase_message["phase_data"], dict)
        assert "original" in phase_message["phase_data"]
        assert '\n\n'.join(phase_message["phase_data"]["customized"].split("\n\n")[1:-1]) == DUMMY_COVER_LETTER
        
        # Verify cover letter template is used
        assert phase_message["phase_data"]["original"] == resume.cover_letter_template
        
        # Test editor update during cover letter phase
        test_update = {
            "type": "update",
            "session_id": session_id,
            "new_value": "Updated Cover Letter"
        }
        websocket.send_json(test_update)
        update_response = json.loads(websocket.receive_text())
        assert update_response["type"] == MessageType.UPDATE
        assert "preview_data" in update_response["phase_data"]
        assert update_response["phase_data"]["preview_data"] == "mock_preview_data"
        
        # Verify ApplicationService state
        assert task.current_phase == ApplicationPhase.COVER_LETTER
        assert task.status == ProcessingStatus.PROCESSING

@pytest.mark.asyncio
async def test_invalid_session_phase_transition(test_client):
    """Test phase transition with invalid session ID."""
    response = test_client.post("/api/apply/cover-letter/invalid-session")
    print(response.json())
    assert response.status_code == 400
    assert "No task found for session" in response.json()['detail']

@pytest.mark.asyncio
async def test_websocket_disconnect_cleanup(test_client, application_service, job_cache):
    """Test cleanup after WebSocket disconnection."""
    # Setup initial connection
    await job_cache.set_job_info(DUMMY_JOB_INFO.jobId, DUMMY_JOB_INFO)
    response = test_client.post(
        f"/api/apply/{DUMMY_JOB_INFO.jobId}",
        json={"apply_type": "easy_apply"}
    )
    session_id = response.json()["session_id"]
    
    # Connect and then disconnect
    with test_client.websocket_connect(f"/ws/editor/{session_id}") as websocket:
        pass  # WebSocket will close here
    
    # Verify cleanup
    assert session_id not in application_service._editor_manager.active_connections