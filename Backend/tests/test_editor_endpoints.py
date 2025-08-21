import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket
from modules.api.websocket.editor_endpoints import EditorEndpoints
from modules.editor.manager import EditorManager
from modules.editor.types import ServerMessage, MessageType, EditorResponse, EditorUpdate, PhaseData
from modules.models.services import ActiveTask, CustomizedContent, ApplyType, ProcessingStatus, ApplicationPhase
from unittest.mock import AsyncMock, patch, MagicMock
import json

class TrackedDict(dict):
    """A dictionary that tracks all operations"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
    
    def __delitem__(self, key):
        super().__delitem__(key)
    
    def clear(self):
        super().clear()

@pytest.fixture
def mock_job_cache():
    cache = AsyncMock()
    cache.get_job_info = AsyncMock()
    cache.set_job_info = AsyncMock()
    return cache

@pytest.fixture
def mock_websocket():
    # Create a MagicMock for synchronous operations
    websocket = MagicMock(spec=WebSocket)
    # Add AsyncMock for async methods
    websocket.receive_json = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.accept = AsyncMock()
    websocket.close = AsyncMock()
    # Make sure the mock can be used as a dictionary value
    websocket.__hash__ = lambda self: id(self)
    return websocket

@pytest.fixture
def editor_manager(mock_job_cache):
    # Create a dictionary to store tasks
    active_tasks = {}
    manager = EditorManager(active_tasks=active_tasks, job_cache=mock_job_cache)
    
    # Mock PDF generation methods
    manager.resume_generator.generate_pdf_from_latex = MagicMock(return_value="mock.pdf")
    manager.cover_letter_generator.generate_pdf_from_latex = MagicMock(return_value="mock.pdf")
    manager._convert_pdf_to_preview = MagicMock(return_value="mock_base64")
    
    # Pre-create a test task
    test_task = ActiveTask(
        job_id="test-job",
        apply_type=ApplyType.EASY,
        session_id="test-session"
    )
    test_task.resume_data = CustomizedContent(
        original="original content",
        customized="customized content"
    )
    active_tasks["test-session"] = test_task
    
    # Initialize active_connections with tracked dict
    manager.active_connections = TrackedDict()
    return manager

@pytest.fixture
def editor_endpoints(editor_manager):
    endpoints = EditorEndpoints(editor_manager)
    return endpoints

@pytest.fixture
def test_client(editor_endpoints):
    return TestClient(editor_endpoints.router)

@pytest.mark.asyncio
async def test_handle_connection_success(editor_endpoints, editor_manager, mock_websocket):
    # Setup
    session_id = "test-session"
    
    # Store original register_client
    original_register = editor_manager.register_client
    
    # Add breakpoint to inspect state during registration
    async def mock_register(*args, **kwargs):
        result = await original_register(*args, **kwargs)
        return result
    
    editor_manager.register_client = mock_register
    
    try:
        # Test - simulate full connection lifecycle
        await editor_endpoints.handle_connection(mock_websocket, session_id)
        
    except Exception as e:
        raise
    finally:
        # Restore original function
        editor_manager.register_client = original_register
    
    # Verify connection setup
    mock_websocket.accept.assert_called_once()
    assert session_id in editor_manager.active_connections
    assert editor_manager.active_connections[session_id] == mock_websocket
    
    # Verify initial state was sent
    mock_websocket.send_text.assert_called_once()
    sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
    assert sent_message["type"] == MessageType.INIT
    assert sent_message["phase_data"]["original"] == "original content"
    assert sent_message["phase_data"]["customized"] == "customized content"

@pytest.mark.asyncio
async def test_handle_connection_invalid_session(editor_endpoints, mock_websocket):
    # Setup
    session_id = "invalid-session"
    
    # Test
    await editor_endpoints.handle_connection(mock_websocket, session_id)
    
    # Verify
    mock_websocket.accept.assert_not_called()
    mock_websocket.close.assert_called_once_with(code=4000, reason="Invalid session ID")

@pytest.mark.asyncio
async def test_handle_message_update(editor_endpoints, editor_manager, mock_websocket):
    # Setup
    client_id = "test-session"
    message = {
        "type": MessageType.UPDATE.value,
        "new_value": "updated content"
    }
    
    # Create update response
    async def mock_handle_update(update):
        if isinstance(update, dict):
            # Convert dict to EditorUpdate
            update = EditorUpdate(
                session_id=client_id,
                new_value=update["new_value"]
            )
        task = editor_manager.active_tasks[client_id]
        task.resume_data.customized = update.new_value
        return EditorResponse(success=True)
    
    # Mock the handle_update method
    with patch.object(editor_manager, 'handle_update', side_effect=mock_handle_update):
        await editor_manager.register_client(client_id, mock_websocket)
        
        # Test
        await editor_endpoints.handle_message(client_id, message)
        
        # Verify message was processed
        assert editor_manager.active_tasks[client_id].resume_data.customized == "updated content"

@pytest.mark.asyncio
async def test_handle_message_invalid_json(editor_endpoints, editor_manager, mock_websocket):
    # Setup
    client_id = "test-session"
    await editor_manager.register_client(client_id, mock_websocket)
    
    # Test
    # We'll simulate the error by passing an invalid message that will trigger a JSONDecodeError
    await editor_endpoints.handle_message(client_id, "invalid json string")
    
    # Verify error message was sent
    mock_websocket.send_text.assert_called_once()
    # Get the raw message that was sent
    sent_raw_message = mock_websocket.send_text.call_args[0][0]
    # Parse it without using the mocked json.loads
    sent_message = json.loads(sent_raw_message)
    assert sent_message["type"] == MessageType.ERROR
    assert "str" in sent_message["error_message"]  # The error will be about string not having 'get' method

@pytest.mark.asyncio
async def test_disconnect(editor_endpoints, editor_manager, mock_websocket):
    # Setup
    client_id = "test-session"
    await editor_manager.register_client(client_id, mock_websocket)
    
    # Test
    await editor_endpoints.disconnect(client_id)
    
    # Verify
    assert client_id not in editor_manager.active_connections

@pytest.mark.asyncio
async def test_handle_connection_websocket_error(editor_endpoints, editor_manager, mock_websocket):
    # Setup
    session_id = "test-session"
    mock_websocket.accept.side_effect = Exception("WebSocket error")
    
    # Test
    await editor_endpoints.handle_connection(mock_websocket, session_id)
    
    # Verify
    mock_websocket.close.assert_called_once()
    assert session_id not in editor_manager.active_connections

@pytest.mark.asyncio
@patch('modules.editor.manager.EditorManager.handle_update')
async def test_handle_message_resume_update(mock_handle_update, editor_endpoints):
    # Setup
    client_id = "test-client"
    message = {"type": MessageType.UPDATE, "new_value": "test resume content"}
    mock_handle_update.return_value = AsyncMock()
    
    # Test
    await editor_endpoints.handle_message(client_id, message)
    
    # Verify
    mock_handle_update.assert_called_once()

@pytest.mark.asyncio
@patch('modules.editor.manager.EditorManager.handle_update')
async def test_handle_message_cover_letter_update(mock_handle_update, editor_endpoints):
    # Setup
    client_id = "test-client"
    message = {"type": MessageType.UPDATE, "new_value": "test cover letter content"}
    mock_handle_update.return_value = AsyncMock()
    
    # Test
    await editor_endpoints.handle_message(client_id, message)
    
    # Verify
    mock_handle_update.assert_called_once()

@pytest.mark.asyncio
@patch('modules.editor.manager.EditorManager.handle_update')
async def test_handle_message_preview_generation(mock_handle_update, editor_endpoints):
    # Setup
    client_id = "test-client"
    message = {"type": MessageType.UPDATE, "new_value": "test content", "generate_preview": True}
    mock_handle_update.return_value = AsyncMock()
    
    # Test
    await editor_endpoints.handle_message(client_id, message)
    
    # Verify
    mock_handle_update.assert_called_once()

@pytest.mark.asyncio
async def test_handle_message_invalid_type(editor_endpoints, editor_manager, mock_websocket):
    # Setup
    client_id = "test-session"
    message = {"type": "invalid_type", "new_value": "test value"}
    
    # Mock handle_update to return a failed response
    editor_manager.handle_update = AsyncMock(return_value=EditorResponse(
        success=False,
        error_message="Session not found"
    ))
    
    await editor_manager.register_client(client_id, mock_websocket)
    
    # Test
    await editor_endpoints.handle_message(client_id, message)
    
    # Verify error was sent through websocket
    mock_websocket.send_text.assert_called_once()
    sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
    assert sent_message["type"] == MessageType.ERROR
    assert "Session not found" in sent_message["error_message"]

@pytest.mark.asyncio
async def test_handle_message_malformed(editor_endpoints, editor_manager, mock_websocket):
    # Setup
    client_id = "test-session"
    message = {"invalid_key": "invalid_value"}
    await editor_manager.register_client(client_id, mock_websocket)
    
    # Test
    await editor_endpoints.handle_message(client_id, message)
    
    # Verify error was sent through websocket
    mock_websocket.send_text.assert_called_once()
    sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
    assert sent_message["type"] == MessageType.ERROR
    # The error will be about missing 'new_value' key
    assert "'new_value'" in sent_message["error_message"]

@pytest.mark.asyncio
async def test_editor_manager_register_client(editor_manager, mock_websocket):
    # Setup
    session_id = "test-session"
    
    # Test
    await editor_manager.register_client(session_id, mock_websocket)
    
    # Verify
    mock_websocket.accept.assert_called_once()
    assert session_id in editor_manager.active_connections
    assert editor_manager.active_connections[session_id] == mock_websocket 