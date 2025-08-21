import json
import os
import base64
from typing import Dict, Optional, Union
import uuid
from fastapi import WebSocket
import logging
import traceback

from vettavista_backend.config import resume
from vettavista_backend.modules.business.cache.job_cache_service import JobCacheService
from vettavista_backend.modules.editor.types import EditorUpdate, EditorResponse, ServerMessage, MessageType, PhaseData
from vettavista_backend.modules.sync.base import SyncManager, DataBroadcaster
from vettavista_backend.modules.generators.resume_generator import ResumeGenerator
from vettavista_backend.modules.utils import DataClassJSONEncoder
from vettavista_backend.modules.generators.cover_letter_generator import CoverLetterGenerator
from vettavista_backend.modules.models.services import ActiveTask, CustomizedContent, ApplicationPhase

logger = logging.getLogger(__name__)

class EditorManager(SyncManager, DataBroadcaster):
    def __init__(self, active_tasks: Dict[str, ActiveTask], job_cache: JobCacheService):
        self.active_tasks = active_tasks
        self._job_cache = job_cache
        self.active_connections: Dict[str, WebSocket] = {}
        self.resume_generator = ResumeGenerator()
        self.cover_letter_generator = CoverLetterGenerator()
        self._id = id(self)
        logger.info(f"Created EditorManager with id {self._id}")

    async def create_session(self, session_id: str, original_latex: str, customized_latex: str) -> str:
        """Create a new editor session with specified ID"""
        task = self.active_tasks.get(session_id)
        if not task:
            raise ValueError(f"No task found for session: {session_id}")
            
        # Store initial resume content
        task.resume_data = CustomizedContent(
            original=original_latex,
            customized=customized_latex
        )
        logger.info(f"Initialized content for session: {session_id}")
        return session_id

    async def broadcast_update(self, message_or_data: Union[ServerMessage, Dict]):
        """Broadcast a message to all connected clients."""
        if isinstance(message_or_data, ServerMessage):
            logger.info(f"Broadcasting message: {json.dumps(message_or_data, cls=DataClassJSONEncoder)}")
        else:
            logger.info(f"Broadcasting message: {message_or_data}")
        
        for client_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(json.dumps(message_or_data, cls=DataClassJSONEncoder))
                logger.info(f"Message sent to client {client_id}")
            except Exception as e:
                logger.error(f"Error sending message to client {client_id}: {e}")

    async def register_client(self, session_id: str, websocket: WebSocket):
        """Register a new WebSocket client."""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"Registered client {session_id}")

    async def unregister_client(self, session_id: str):
        """Unregister a WebSocket client."""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"Unregistered client {session_id}")

    async def handle_client_message(self, client_id: str, message: Dict) -> None:
        """Handle an incoming message from a client."""
        update = EditorUpdate(
            session_id=client_id,
            new_value=message.get("new_value", "")
        )
        await self.handle_update(update)

    async def get_client_state(self, client_id: str) -> Dict:
        """Get the current state for a client."""
        task = self.active_tasks.get(client_id)
        if not task:
            return {}
        
        # Get the appropriate content based on phase
        if task.current_phase == ApplicationPhase.COVER_LETTER:
            content = task.cover_letter_data
        else:
            content = task.resume_data
        
        if not content:
            return {}
        
        return {
            "original_latex": content.original,
            "customized_latex": content.customized
        }

    def _convert_pdf_to_preview(self, pdf_path: str) -> Optional[str]:
        """Convert PDF to base64 string for preview."""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_data = file.read()
                base64_data = base64.b64encode(pdf_data).decode('utf-8')
                return base64_data
        except Exception as e:
            logger.error(f"Failed to convert PDF to base64: {e}")
            traceback.print_exc()
            return None

    async def handle_update(self, update: EditorUpdate) -> EditorResponse:
        """Handle an update from the editor"""
        task = self.active_tasks.get(update.session_id)
        if not task:
            return EditorResponse(success=False, error_message="Session not found")

        try:
            # Update appropriate content based on phase
            if task.current_phase == ApplicationPhase.COVER_LETTER:
                if not task.cover_letter_data:
                    task.cover_letter_data = CustomizedContent(
                        original=resume.cover_letter_template,
                        customized=update.new_value
                    )
                else:
                    task.cover_letter_data.customized = update.new_value
                
                # Get job info for company name
                job_info = await self._job_cache.get_job_info(task.job_id)
                if not job_info:
                    raise ValueError(f"No job info found for session: {update.session_id}")
                
                # Generate PDF
                pdf_path = self.cover_letter_generator.generate_pdf_from_text(
                    text=task.cover_letter_data.customized,
                    output_filename=f"customized_cover_letter_{update.session_id}"
                )
            else:
                if not task.resume_data:
                    raise ValueError("No resume data available")
                task.resume_data.customized = update.new_value
                
                # Generate PDF
                pdf_path = self.resume_generator.generate_pdf_from_latex(
                    task.resume_data.customized,
                    f"customized_resume_{update.session_id}"
                )

            # Convert PDF to base64
            preview_data = self._convert_pdf_to_preview(pdf_path)
            if preview_data:
                task.preview_data = preview_data
                logger.info(f"Generated preview for session {update.session_id}")
            
            # Broadcast update
            current_content = task.cover_letter_data if task.current_phase == ApplicationPhase.COVER_LETTER else task.resume_data
            await self.broadcast_update(ServerMessage(
                type=MessageType.UPDATE,
                phase_data=PhaseData(
                    original=current_content.original,
                    customized=current_content.customized,
                    preview_data=task.preview_data
                )
            ))
            return EditorResponse(success=True)
            
        except Exception as e:
            logger.error(f"Error handling update: {str(e)}")
            return EditorResponse(success=False, error_message=f"Internal error: {str(e)}")

    def get_task_by_session_id(self, session_id: str) -> Optional[ActiveTask]:
        """Get a session by ID"""
        task = self.active_tasks.get(session_id)
        if not task:
            logger.error(f"Session not found: {session_id}")
        return task