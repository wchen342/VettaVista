import json
import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket
from modules.editor.manager import EditorManager
from modules.editor.types import (
    ServerMessage,
    MessageType,
    PhaseData,
    EditorUpdate,
    EditorResponse
)
from modules.models.services import (
    ApplicationPhase,
    ActiveTask,
    ApplyType,
    ProcessingStatus,
    CustomizedContent
)
from modules.utils import DataClassJSONEncoder
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.fixture
def active_tasks():
    """Fixture to provide a dictionary of active tasks"""
    return {}

@pytest.fixture
def mock_job_cache():
    cache = AsyncMock()
    cache.get_job_info = AsyncMock()
    cache.set_job_info = AsyncMock()
    return cache

@pytest.fixture
def editor_manager(active_tasks, mock_job_cache):
    with patch('modules.generators.resume_generator.ResumeGenerator') as mock_generator:
        manager = EditorManager(active_tasks=active_tasks, job_cache=mock_job_cache)
        manager.resume_generator = mock_generator
        yield manager

@pytest.fixture
def mock_websocket():
    websocket = AsyncMock(spec=WebSocket)
    websocket.send_text = AsyncMock()
    return websocket

@pytest.fixture
def test_task(active_tasks):
    """Create a test task and add it to active_tasks"""
    task = ActiveTask(
        job_id="test-job",
        apply_type=ApplyType.EASY,
        session_id="test-session"
    )
    active_tasks["test-session"] = task
    return task

@pytest.fixture
async def setup_session(editor_manager, mock_websocket, test_task):
    session_id = "test-session"
    await editor_manager.create_session(
        session_id=session_id,
        original_latex="original",
        customized_latex="customized"
    )
    await editor_manager.register_client(session_id, mock_websocket)
    return session_id, mock_websocket

@pytest.mark.asyncio
async def test_broadcast_update_with_dict(editor_manager, mock_websocket):
    # Setup
    session_id = "test-session"
    await editor_manager.register_client(session_id, mock_websocket)
    
    # Test
    test_data = {"key": "value"}
    await editor_manager.broadcast_update(test_data)
    
    # Verify
    mock_websocket.send_text.assert_called_once()
    sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
    # The manager sends dict data directly without wrapping
    assert sent_message == test_data

@pytest.mark.asyncio
async def test_broadcast_update_with_server_message(editor_manager, mock_websocket):
    # Setup
    session_id = "test-session"
    await editor_manager.register_client(session_id, mock_websocket)
    
    # Test
    message = ServerMessage(type=MessageType.PHASE_CHANGE, phase=ApplicationPhase.RESUME)
    await editor_manager.broadcast_update(message)
    
    # Verify
    mock_websocket.send_text.assert_called_once()
    sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
    assert sent_message["type"] == MessageType.PHASE_CHANGE
    assert sent_message["phase"] == ApplicationPhase.RESUME.value

@pytest.mark.asyncio
@patch('modules.generators.resume_generator.ResumeGenerator.generate_pdf_from_latex')
@patch('modules.editor.manager.EditorManager._convert_pdf_to_preview')
async def test_handle_update(mock_convert_pdf, mock_generate_pdf, editor_manager):
    # Setup
    mock_generate_pdf.return_value = "test.pdf"
    mock_convert_pdf.return_value = "test-png-data"
    update = AsyncMock()
    
    # Test
    result = await editor_manager.handle_update(update)
    
    # Verify
    assert result.success
    mock_generate_pdf.assert_called_once()
    mock_convert_pdf.assert_called_once_with("test.pdf")

@pytest.mark.asyncio
async def test_create_session(editor_manager, test_task):
    # Test
    session_id = "test-session"
    await editor_manager.create_session(
        session_id=session_id,
        original_latex="original",
        customized_latex="customized"
    )
    
    # Verify
    task = editor_manager.active_tasks[session_id]
    assert task.resume_data is not None
    assert task.resume_data.original == "original"
    assert task.resume_data.customized == "customized"

@pytest.mark.asyncio
async def test_get_nonexistent_session(editor_manager):
    task = editor_manager.get_task_by_session_id("nonexistent")
    assert task is None

@pytest.mark.asyncio
async def test_client_registration_lifecycle(editor_manager, mock_websocket):
    # Test registration
    session_id = "test-session"
    await editor_manager.register_client(session_id, mock_websocket)
    assert session_id in editor_manager.active_connections
    
    # Test unregistration
    await editor_manager.unregister_client(session_id)
    assert session_id not in editor_manager.active_connections

@pytest.mark.asyncio
async def test_handle_update(editor_manager, setup_session):
    session_id, mock_websocket = await setup_session
    
    # Setup mock for PDF generation
    editor_manager.resume_generator.generate_pdf_from_latex.return_value = "test.pdf"
    with patch.object(editor_manager, '_convert_pdf_to_preview', return_value="test-png-data"):
        # Test
        update = EditorUpdate(session_id=session_id, new_value="updated latex")
        result = await editor_manager.handle_update(update)
        
        # Verify
        assert result.success
        editor_manager.resume_generator.generate_pdf_from_latex.assert_called_once()
        
        # Verify broadcast
        mock_websocket.send_text.assert_called_once()
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["type"] == MessageType.UPDATE.value
        assert sent_message["phase_data"]["original"] == "original"
        assert sent_message["phase_data"]["customized"] == "updated latex"
        assert sent_message["phase_data"]["preview_data"] == "test-png-data"

@pytest.mark.asyncio
async def test_handle_update_invalid_session(editor_manager):
    update = EditorUpdate(session_id="nonexistent", new_value="test")
    response = await editor_manager.handle_update(update)
    assert not response.success
    assert "Session not found" in response.error_message

@pytest.mark.asyncio
async def test_handle_update_pdf_generation_failure(editor_manager, setup_session):
    session_id, mock_websocket = await setup_session
    
    # Setup mock to simulate PDF generation failure
    editor_manager.resume_generator.generate_pdf_from_latex.side_effect = Exception("PDF generation failed")
    
    # Test
    update = EditorUpdate(session_id=session_id, new_value="updated latex")
    response = await editor_manager.handle_update(update)
    
    # Verify
    assert not response.success  # PDF generation failure should fail the update
    assert "PDF generation failed" in response.error_message
    
    # Verify no broadcast was made
    mock_websocket.send_text.assert_not_called()

@pytest.mark.asyncio
async def test_broadcast_phase_change(editor_manager, setup_session):
    session_id, mock_websocket = await setup_session
    
    # Test
    phase_data = PhaseData(original="original", customized="customized")
    message = ServerMessage(
        type=MessageType.PHASE_CHANGE,
        phase=ApplicationPhase.COVER_LETTER,
        phase_data=phase_data
    )
    await editor_manager.broadcast_update(message)
    
    # Verify
    mock_websocket.send_text.assert_called_once()
    sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
    assert sent_message["type"] == MessageType.PHASE_CHANGE
    assert sent_message["phase"] == "cover_letter"
    assert "phase_data" in sent_message

@pytest.mark.asyncio
async def test_get_client_state(editor_manager, setup_session):
    session_id, _ = await setup_session
    
    # Ensure task has proper data structure
    task = editor_manager.active_tasks[session_id]
    task.resume_data = CustomizedContent(
        original="original",
        customized="customized"
    )
    task.current_phase = ApplicationPhase.RESUME
    
    # Test
    state = await editor_manager.get_client_state(session_id)
    
    # Verify
    assert state["original_latex"] == "original"
    assert state["customized_latex"] == "customized"

@pytest.mark.asyncio
async def test_get_client_state_no_session(editor_manager):
    state = await editor_manager.get_client_state("nonexistent")
    assert state == {} 