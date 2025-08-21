from typing import Dict, Any

from fastapi import status, Depends, Body

from vettavista_backend.modules.api.rest.base import BaseRESTEndpoint
from vettavista_backend.modules.api.utils import handle_endpoint_errors
from vettavista_backend.modules.business.application.application_service import ApplicationService
from vettavista_backend.modules.models.services import ApplyRequest, FinalizeRequest


class ApplicationEndpoints(BaseRESTEndpoint):
    def __init__(self, application_service: ApplicationService):
        self._application_service = application_service
        super().__init__()

    def get_application_service(self) -> ApplicationService:
        return self._application_service

    def setup_routes(self):
        @self.router.post("/api/apply/{job_id}")
        async def apply_for_job(
            job_id: str,
            request: ApplyRequest = Body(...),
            application_service: ApplicationService = Depends(lambda: self._application_service)
        ):
            """Start application process for a job"""
            result = await application_service.handle_apply(job_id, request.apply_type)
            return result

        @self.router.post("/api/editor/finalize", status_code=status.HTTP_204_NO_CONTENT)
        @handle_endpoint_errors
        async def finalize_application(
            request: FinalizeRequest = Body(...)  # Use the model
        ) -> None:
            """Finalize application after both phases are complete"""
            await self._application_service.finalize_application(
                session_id=request.session_id,
                content=request.content
            )

        @self.router.post("/api/apply/cover-letter/{session_id}", status_code=status.HTTP_202_ACCEPTED)
        @handle_endpoint_errors
        async def handle_cover_letter_phase(
            session_id: str
        ) -> Dict[str, Any]:
            """Transition to cover letter phase"""
            return await self._application_service.start_cover_letter_phase(session_id)

        @self.router.post("/api/editor/back-to-resume/{session_id}")
        @handle_endpoint_errors
        async def back_to_resume_phase(
            session_id: str,
        ) -> Dict[str, Any]:
            """Return to resume phase from cover letter"""
            return await self._application_service.back_to_resume_phase(session_id) 