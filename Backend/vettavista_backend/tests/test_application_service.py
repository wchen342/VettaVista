import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from config import resume

from modules.editor.types import ServerMessage, MessageType, PhaseData
from modules.models.services import ApplyType, ProcessingStatus, ApplicationPhase, ActiveTask, JobDetailedInfo, \
    CustomizedContent, GlassdoorRating
from modules.ai.protocols import ClaudeServiceProtocol
from modules.business.application.application_service import ApplicationService
from modules.storage.job_history_storage import JobHistoryStorage
from modules.editor.manager import EditorManager

from config.global_constants import STORAGE_SETTINGS
from tests.conftest import create_test_resume


@pytest.fixture
def mock_job_info():
    return JobDetailedInfo(
        jobId="test-job",
        title="Test Job",
        company="Test Company",
        location="Test Location",
        description="Test Description",
        url="http://test.com",
        requirements="Test Requirements",
        aboutCompany="Test About",
        companySize="100-500",
        glassdoorRating=GlassdoorRating(rating=3., reviewCount=10, isValid=False)
    )

@pytest.fixture
def mock_broadcaster():
    # Create a basic mock object
    mock = MagicMock()
    # Attach an AsyncMock for the async method
    mock.broadcast_update = AsyncMock()
    return mock

@pytest.fixture
def mock_claude():
    mock = MagicMock(spec=ClaudeServiceProtocol)
    mock.customize_resume = AsyncMock()
    mock.customize_cover_letter = AsyncMock()
    return mock

@pytest.fixture
def mock_job_cache():
    cache = AsyncMock()
    cache.get_job_info = AsyncMock()
    cache.set_job_info = AsyncMock()
    return cache

@pytest.fixture
def mock_job_history():
    history = MagicMock()
    history.add_or_update_job = AsyncMock()
    return history

@pytest.fixture
def mock_editor_manager():
    manager = MagicMock(spec=EditorManager)
    manager.active_tasks = {}
    manager.create_session = AsyncMock()
    manager.broadcast_update = AsyncMock()
    return manager

@pytest.fixture
def application_service(mock_job_cache, mock_job_history, mock_editor_manager, mock_broadcaster, mock_claude):
    return ApplicationService(
        job_cache=mock_job_cache,
        job_history=mock_job_history,
        editor_manager=mock_editor_manager,
        broadcaster=mock_broadcaster,
        claude_service=mock_claude
    )

@pytest.fixture
async def active_application(application_service, mock_job_cache, mock_claude, mock_job_info) -> str:
    """Fixture to create an active application and return its session ID"""
    mock_resume = create_test_resume()
    mock_claude.customize_resume.return_value = (mock_resume, mock_resume)
    mock_job_cache.get_job_info.return_value = mock_job_info
    
    result = await application_service.handle_apply("test-job", ApplyType.EASY)
    return result["session_id"]

@pytest.fixture
def temp_job_history_file():
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_path = temp_file.name
    yield temp_path
    # Clean up after test
    Path(temp_path).unlink(missing_ok=True)

@pytest.fixture
def job_history(temp_job_history_file):
    with patch('modules.storage.job_history_storage.STORAGE_SETTINGS', 
              {'history_file': temp_job_history_file}):
        return JobHistoryStorage()

class TestHandleApply:
    @pytest.mark.asyncio
    async def test_handle_apply_creates_task(self, application_service, mock_claude):
        """Test that handle_apply creates a task with correct initial state"""
        # Setup
        job_id = "test-job"
        mock_resume = create_test_resume()
        mock_claude.customize_resume.return_value = (mock_resume, mock_resume)
        
        # Test
        result = await application_service.handle_apply(job_id, ApplyType.EASY)
        
        # Verify
        assert "session_id" in result
        assert "editor_url" in result
        task = application_service._editor_manager.active_tasks[result["session_id"]]
        assert task.job_id == job_id
        assert task.status == ProcessingStatus.PENDING
        assert task.current_phase == ApplicationPhase.RESUME

    @pytest.mark.asyncio
    async def test_handle_apply_creates_editor_session(self, application_service, mock_editor_manager, mock_claude, mock_job_info):
        """Test that handle_apply properly initializes editor session"""
        # Setup
        job_id = "test-job"
        mock_resume = create_test_resume()
        mock_claude.customize_resume.return_value = (mock_resume, mock_resume)
        application_service._job_cache.get_job_info.return_value = mock_job_info
        
        # Test
        result = await application_service.handle_apply(job_id, ApplyType.EASY)
        
        # Verify
        mock_editor_manager.create_session.assert_called_once()
        call_args = mock_editor_manager.create_session.call_args[1]
        assert call_args["session_id"] == result["session_id"]

    @pytest.mark.asyncio
    async def test_handle_apply_caches_job_info(self, application_service, mock_job_cache, mock_claude):
        """Test that handle_apply caches job information"""
        # Setup
        job_id = "test-job"
        mock_resume = create_test_resume()
        mock_claude.customize_resume.return_value = (mock_resume, mock_resume)
        
        # Test
        await application_service.handle_apply(job_id, ApplyType.EASY)
        
        # Verify
        mock_job_cache.get_job_info.assert_called_once_with(job_id)

class TestStartCoverLetterPhase:
    @pytest.mark.asyncio
    async def test_start_cover_letter_phase_updates_task(self, application_service, mock_claude):
        """Test that start_cover_letter_phase updates task state correctly"""
        # Setup
        session_id = "test-session"
        job_id = "test-job"
        mock_resume = create_test_resume()
        application_service._editor_manager.active_tasks[session_id] = ActiveTask(
            job_id=job_id,
            apply_type=ApplyType.EASY,
            status=ProcessingStatus.COMPLETED,
            current_phase=ApplicationPhase.RESUME,
            resume_data=CustomizedContent(
                original="Main letter content",
                customized="Main letter content"
            )
        )
        mock_claude.customize_cover_letter.return_value = "test letter"
        
        # Test
        result = await application_service.start_cover_letter_phase(session_id)
        
        # Verify
        assert result["session_id"] == session_id
        task = application_service._editor_manager.active_tasks[session_id]
        assert task.current_phase == ApplicationPhase.COVER_LETTER

    @pytest.mark.asyncio
    async def test_start_cover_letter_phase_invalid_session(self, application_service):
        """Test that start_cover_letter_phase handles invalid session IDs"""
        with pytest.raises(ValueError, match="No task found for session"):
            await application_service.start_cover_letter_phase("invalid-session")

    @pytest.mark.asyncio
    async def test_start_cover_letter_phase_broadcasts_update(
        self, application_service, mock_editor_manager, mock_claude
    ):
        """Test that phase change is broadcast to editor"""
        # Setup
        session_id = "test-session"
        job_id = "test-job"
        mock_resume = create_test_resume()
        application_service._editor_manager.active_tasks[session_id] = ActiveTask(
            job_id=job_id,
            apply_type=ApplyType.EASY,
            status=ProcessingStatus.COMPLETED,
            current_phase=ApplicationPhase.RESUME,
            resume_data=CustomizedContent(
                original="\\documentclass{article}\n\\begin{document}\nOriginal Resume\n\\end{document}",
                customized="\\documentclass{article}\n\\begin{document}\nCustomized Resume\n\\end{document}"
            )
        )
        mock_claude.customize_cover_letter.return_value = "test letter"
        
        # Test
        await application_service.start_cover_letter_phase(session_id)
        
        # Verify
        mock_editor_manager.broadcast_update.assert_called_once_with(
            ServerMessage(
                type=MessageType.PHASE_CHANGE,
                phase=ApplicationPhase.COVER_LETTER,
                phase_data=PhaseData(
                    original=resume.cover_letter_template,  # Use actual template
                    customized="test letter"
                )
            )
        )

class TestFinalizeApplication:
    @pytest.mark.asyncio
    async def test_finalize_updates_job_history(self, application_service, mock_job_history, mock_job_info):
        """Test that finalize_application updates job history"""
        # Setup
        session_id = "test-session"
        job_id = "test-job"
        mock_resume = create_test_resume()
        application_service._editor_manager.active_tasks[session_id] = ActiveTask(
            job_id=job_id,
            apply_type=ApplyType.EASY,
            status=ProcessingStatus.COMPLETED,
            current_phase=ApplicationPhase.COVER_LETTER,
            resume_data={
                'customized': mock_resume,
                'original': mock_resume
            },
            cover_letter_data="test cover letter"
        )
        application_service._job_cache.get_job_info.return_value = mock_job_info
        
        # Test
        await application_service.finalize_application(session_id, "test content")
        
        # Verify
        mock_job_history.add_or_update_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_finalize_invalid_session(self, application_service):
        """Test that finalize_application handles invalid session IDs"""
        with pytest.raises(ValueError, match="No task found for session"):
            await application_service.finalize_application("invalid-session", "content")

    @pytest.mark.asyncio
    async def test_finalize_updates_task_status(self, application_service, mock_job_info):
        """Test that finalize_application updates task status correctly"""
        # Setup
        session_id = "test-session"
        job_id = "test-job"
        mock_resume = create_test_resume()
        application_service._editor_manager.active_tasks[session_id] = ActiveTask(
            job_id=job_id,
            apply_type=ApplyType.EASY,
            status=ProcessingStatus.PROCESSING,
            current_phase=ApplicationPhase.COVER_LETTER,
            resume_data={
                'customized': mock_resume,
                'original': mock_resume
            },
            cover_letter_data="test cover letter"
        )
        application_service._job_cache.get_job_info.return_value = mock_job_info
        
        # Test
        await application_service.finalize_application(session_id, "test content")
        
        # Verify
        task = application_service._editor_manager.active_tasks[session_id]
        assert task.status == ProcessingStatus.COMPLETED
        assert task.current_phase == ApplicationPhase.FINALIZED 