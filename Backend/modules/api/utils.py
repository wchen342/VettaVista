from typing import Dict, Tuple, Callable
from functools import wraps
import logging
from fastapi import HTTPException
import traceback

logger = logging.getLogger(__name__)

def handle_endpoint_errors(func: Callable):
    """Decorator to handle common error patterns in HTTP endpoints"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
            # Return empty dict for None responses
            if result is None:
                return {}
            return result
        except HTTPException:
            # Re-raise HTTP exceptions as they're already properly formatted
            raise
        except (KeyError, ValueError) as e:
            # Handle missing required fields and validation errors as 400
            logger.error(str(e))
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            logger.error(f"Error details: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))
    return wrapper
