import asyncio
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Global semaphore to limit concurrent requests
api_semaphore = asyncio.Semaphore(2)  # Allow max 2 concurrent requests

class RequestLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        async with api_semaphore:
            logger.info(f"Processing request to {request.url.path}")
            response = await call_next(request)
            return response 