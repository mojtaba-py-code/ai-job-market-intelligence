"""Exception handlers mapping domain errors to HTTP responses."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..exceptions import JMIError
from ..logging import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(JMIError)
    async def _handle_jmi_error(_request: Request, exc: JMIError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("unhandled_domain_error", code=exc.code, error=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "detail": exc.message},
            headers=({"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        # Never leak internal details to the client.
        logger.error("internal_error", error=str(exc), exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": "An unexpected error occurred."},
        )
