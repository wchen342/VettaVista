import asyncio
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from typing import Dict, Any, Optional, List

from platformdirs import user_documents_dir

from vettavista_backend.config import resume, personals, ResumeModel
from vettavista_backend.config.global_constants import ApplicationStatus, JobStatus, APP_NAME
from vettavista_backend.modules.ai import ClaudeServiceProtocol
from vettavista_backend.modules.ai.claude_connections import ClaudeService
from vettavista_backend.modules.business.cache.job_cache_service import JobCacheService
from vettavista_backend.modules.editor.manager import EditorManager
from vettavista_backend.modules.editor.types import PhaseData, ServerMessage, MessageType
from vettavista_backend.modules.generators.cover_letter_generator import CoverLetterGenerator
from vettavista_backend.modules.generators.resume_generator import ResumeGenerator
from vettavista_backend.modules.models.services import ActiveTask, ProcessingStatus, ApplyType, ApplicationPhase, \
    CustomizedContent
from vettavista_backend.modules.models.storage import JobHistoryEntry
from vettavista_backend.modules.storage.job_history_storage import JobHistoryStorage
from vettavista_backend.modules.sync.base import DataBroadcaster

logger = logging.getLogger(__name__)

class ApplicationService:
    MAX_PARALLEL_JOBS = 2

    def __init__(
        self,
        job_cache: JobCacheService,
        job_history: JobHistoryStorage,
        editor_manager: EditorManager,
        broadcaster: DataBroadcaster,
        claude_service: Optional[ClaudeServiceProtocol] = None
    ):
        """Initialize the application service.
        
        Args:
            job_cache: Cache service for job data
            job_history: Storage service for job history
            editor_manager: Manager for editor sessions
            broadcaster: Broadcaster for sync updates
        """
        self._job_cache = job_cache
        self._job_history = job_history
        self._processing_semaphore = asyncio.Semaphore(self.MAX_PARALLEL_JOBS)
        self._resume_generator = ResumeGenerator()
        self._cover_letter_generator = CoverLetterGenerator()
        self._claude = claude_service or ClaudeService()
        self._editor_manager = editor_manager
        self._broadcaster = broadcaster
        
        # Create output directory for finalized documents
        self.finalized_dir = os.path.join(user_documents_dir(), APP_NAME, "applications")  # Move outside generated/
        if not os.path.exists(self.finalized_dir):
            os.makedirs(self.finalized_dir)

    def _filter_skills(self, resume_model: ResumeModel) -> tuple[ResumeModel, List[str]]:
        """Filter out language and recommended skills from resume model."""
        filtered_skills = {}
        recommended_skills = []
        
        for category, items in resume_model.skills.items():
            category_lower = category.lower()
            if category_lower == 'recommended skills':
                recommended_skills = items  # Just take the list directly
            elif category_lower not in ['language', 'languages']:
                filtered_skills[category] = items
        
        # Create new resume model with filtered skills
        filtered_resume = replace(resume_model, skills=filtered_skills)
        
        return filtered_resume, recommended_skills

    async def handle_apply(self, job_id: str, apply_type: ApplyType) -> Dict[str, Any]:
        """Handle job application initiation"""
        logger.info(f"Starting application process for job {job_id}")
        
        task = ActiveTask(job_id=job_id, apply_type=apply_type)
        self._editor_manager.active_tasks[task.session_id] = task
        task.status = ProcessingStatus.PROCESSING
        
        try:
            # Get job info from cache
            job_info = await self._job_cache.get_job_info(task.job_id)
            if not job_info:
                raise ValueError(f"No cached job info found for job_id: {task.job_id}")
            
            # Customize resume using Claude
            original_resume, customized_resume = await self._claude.customize_resume(job_info, self._job_cache)
            
            # Filter skills and get recommended skills
            filtered_resume, recommended_skills = self._filter_skills(customized_resume)
            task.recommended_skills = recommended_skills
            
            # Generate LaTeX content
            original_latex = self._resume_generator.generate_latex(original_resume)
            customized_latex = self._resume_generator.generate_latex(filtered_resume)
            
            # Create editor session
            await self._editor_manager.create_session(
                session_id=task.session_id,
                original_latex=original_latex,
                customized_latex=customized_latex,
            )
            
            # Cache results
            task.resume_data = CustomizedContent(
                original=original_latex,
                customized=customized_latex
            )
            task.status = ProcessingStatus.PENDING
            
            logger.info(f"Successfully customized resume for job {task.job_id}")
            return {
                "session_id": task.session_id,
                "editor_url": f"/editor?session={task.session_id}"
            }
            
        except Exception as e:
            logger.error(f"Error in resume phase for job {task.job_id}: {str(e)}")
            task.status = ProcessingStatus.FAILED
            task.error = str(e)
            raise

    async def finalize_application(self, session_id: str, content: str) -> None:
        """Finalize the application after both phases are complete"""
        logger.info(f"Finalizing application for session {session_id}")
        
        if session_id not in self._editor_manager.active_tasks:
            raise ValueError(f"No task found for session: {session_id}")
        
        task = self._editor_manager.active_tasks[session_id]
        job_info = await self._job_cache.get_job_info(task.job_id)
        if not job_info:
            raise ValueError(f"No job info found for job {task.job_id}")
        
        # Update content based on current phase
        if task.current_phase == ApplicationPhase.COVER_LETTER:
            task.cover_letter_data.customized = content
        else:
            raise ValueError("Can only finalize from cover letter phase")
            
        # Only finalize when both phases are complete
        if task.resume_data and task.cover_letter_data:
            try:
                # Generate PDFs with same names as in editor's handle_update
                resume_temp = self._resume_generator.generate_pdf_from_latex(
                    task.resume_data.customized,
                    f"resume_{session_id}"  # Match editor's filename pattern
                )
                
                cover_letter_temp = self._cover_letter_generator.generate_pdf_from_text(
                    task.cover_letter_data.customized,
                    f"cover_letter_{session_id}"  # Match editor's filename pattern
                )
                
                # Create job-specific directory if it doesn't exist
                job_dir = os.path.join(self.finalized_dir, task.job_id)
                os.makedirs(job_dir, exist_ok=True)
                
                # Define final paths
                name_suffix = f"{personals.first_name}_{personals.last_name}".lower()
                resume_path = os.path.join(job_dir, f"resume_{name_suffix}.pdf")
                cover_letter_path = os.path.join(job_dir, f"cover_letter_{name_suffix}.pdf")
                
                # Copy files to final destination
                shutil.copy2(resume_temp, resume_path)
                shutil.copy2(cover_letter_temp, cover_letter_path)
                
                # Get job status from cache
                filter_result = await self._job_cache.get_filter_result(task.job_id)
                match_status = filter_result.status if filter_result else JobStatus.UNKNOWN
                
                # Create job history entry with the final paths
                entry = JobHistoryEntry(
                    job_id=task.job_id,
                    title=job_info.title,
                    company=job_info.company,
                    location=job_info.location,
                    url=job_info.url or "",
                    match_status=match_status,
                    application_status=ApplicationStatus.APPLIED,
                    rejection_reason="",
                    skip_reason="",
                    user_notes="",
                    date_created=datetime.now().isoformat(),
                    date_updated=datetime.now().isoformat(),
                    date_applied=datetime.now().isoformat(),
                    resume_path=resume_path,
                    cover_letter_path=cover_letter_path
                )
                
                await self._job_history.add_or_update_job(entry)
                task.status = ProcessingStatus.COMPLETED
                task.current_phase = ApplicationPhase.FINALIZED
                
                # Add broadcast after successful finalization
                history = await self._job_history.search_jobs(days=30)  # Get recent history
                await self._broadcaster.broadcast_update({
                    "history": history
                })

                # Open job directory in native file browser with proper detachment
                try:
                    if os.name == 'nt':  # Windows
                        # Use CREATE_NEW_PROCESS_GROUP flag
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        subprocess.Popen(
                            ['explorer', job_dir],
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                            startupinfo=startupinfo
                        )
                    else:  # Mac/Linux
                        command = ['open', job_dir] if sys.platform == 'darwin' else ['xdg-open', job_dir]
                        subprocess.Popen(
                            command,
                            start_new_session=True,  # Detach from parent process group
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                except Exception as e:
                    logger.warning(f"Could not open job directory: {str(e)}")
                
                logger.info(f"Successfully finalized application for job {task.job_id}")
            except Exception as e:
                logger.error(f"Error in finalize_application: {str(e)}")
                task.status = ProcessingStatus.FAILED
                task.error = str(e)
                raise
        else:
            logger.error(f"Error finalizing application for job {task.job_id}: missing expected data")

    async def start_cover_letter_phase(self, session_id: str) -> Dict[str, Any]:
        """Transition to cover letter phase"""
        logger.info(f"Starting cover letter phase for session {session_id}")
        
        if session_id not in self._editor_manager.active_tasks:
            raise ValueError(f"No task found for session: {session_id}")
        
        task = self._editor_manager.active_tasks[session_id]
        task.status = ProcessingStatus.PROCESSING
        
        try:
            # Get job info from cache
            job_info = await self._job_cache.get_job_info(task.job_id)

            # First check if we have user-customized content
            if task.cover_letter_data and task.cover_letter_data.customized:
                logger.info(f"Using user-customized cover letter for job {task.job_id}")
                complete_letter = task.cover_letter_data.customized
            else:
                # Check if we have cached Claude output
                cached_content = await self._job_cache.get_cover_letter(task.job_id)
                if cached_content:
                    logger.info(f"Using cached Claude output for job {task.job_id}")
                    generated_body = cached_content
                else:
                    # Generate new cover letter if no cache exists
                    logger.info(f"Generating new cover letter for job {task.job_id}")
                    generated_body = await self._claude.customize_cover_letter(
                        task.resume_data.customized,
                        job_info,
                        self._job_cache
                    )
                
                # Generate complete letter with header/footer
                complete_letter = self._cover_letter_generator.generate_body(
                    company_name=job_info.company,
                    content=generated_body
                )
            
            # Store/update the task data
            task.cover_letter_data = CustomizedContent(
                original=resume.cover_letter_template,
                customized=complete_letter
            )
            
            # Broadcast phase change
            phase_data = PhaseData(
                original=resume.cover_letter_template,
                customized=complete_letter
            )
            await self._editor_manager.broadcast_update(ServerMessage(
                type=MessageType.PHASE_CHANGE,
                phase=ApplicationPhase.COVER_LETTER,
                phase_data=phase_data
            ))
            
            task.current_phase = ApplicationPhase.COVER_LETTER
            task.status = ProcessingStatus.PROCESSING
            
            logger.info(f"Successfully started cover letter phase for session {session_id}")
            return {
                "session_id": session_id,
                "phase": ApplicationPhase.COVER_LETTER.value
            }
            
        except Exception as e:
            logger.error(f"Error starting cover letter phase for session {session_id}: {str(e)}")
            task.status = ProcessingStatus.FAILED
            task.error = str(e)
            raise

    async def back_to_resume_phase(self, session_id: str) -> Dict[str, Any]:
        """Return to resume phase from cover letter"""
        logger.info(f"Returning to resume phase for session {session_id}")
        
        if session_id not in self._editor_manager.active_tasks:
            raise ValueError(f"No task found for session: {session_id}")
        
        task = self._editor_manager.active_tasks[session_id]
        
        # Verify we're actually in cover letter phase
        if task.current_phase != ApplicationPhase.COVER_LETTER:
            raise ValueError("Can only return to resume phase from cover letter phase")
            
        task.current_phase = ApplicationPhase.RESUME

        try:
            # Get the stored resume data
            if not task.resume_data:
                raise ValueError("No resume data available")
            
            phase_data = PhaseData(
                original=task.resume_data.original,
                customized=task.resume_data.customized
            )

            # Broadcast phase change to all clients
            await self._editor_manager.broadcast_update(ServerMessage(
                type=MessageType.PHASE_CHANGE,
                phase=ApplicationPhase.RESUME,
                phase_data=phase_data
            ))
            
            logger.info(f"Successfully returned to resume phase for session {session_id}")
            return {
                "session_id": session_id,
                "phase": ApplicationPhase.RESUME.value
            }
            
        except Exception as e:
            logger.error(f"Error returning to resume phase for session {session_id}: {str(e)}")
            task.status = ProcessingStatus.FAILED
            task.error = str(e)
            raise