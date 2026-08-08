"""Exception handling skeleton.

Provides a base application error type and centralized exception handlers.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for application-level errors."""

    def __init__(self, message: str, code: str = "app_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def register_exception_handlers(app: FastAPI) -> None:
    """Register centralized exception handlers on the application."""

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"code": exc.code, "detail": exc.message},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "internal_error", "detail": "Internal server error"},
        )
