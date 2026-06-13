"""
Error helpers for FastAPI routers.

Provides log_and_raise_from_request(), which:
  1. Stashes structured error info on request.state.error_info so the
     RequestLoggingMiddleware can fold it into the api_log row.
  2. Raises an HTTPException with the request_id as the correlation ID
     so the frontend can surface it to the user.
"""

import traceback
from fastapi import HTTPException
from starlette.requests import Request


def log_and_raise_from_request(exc: Exception, request: Request, status_code: int = 500) -> None:
    """
    Attach error details to request.state and raise an HTTPException.

    The RequestLoggingMiddleware reads request.state.error_info after the
    response is complete and writes it into the api_log row for this request.
    """
    tb = traceback.format_exc()
    request.state.error_info = {
        "error_type":    type(exc).__name__,
        "error_message": str(exc),
        "traceback":     tb,
    }

    request_id = getattr(request.state, "request_id", None)
    detail = {
        "error":      str(exc),
        "request_id": request_id,
    }
    raise HTTPException(status_code=status_code, detail=detail)