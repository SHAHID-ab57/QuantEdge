"""Exception handling skeleton.

Provides a base application error type and centralized exception handlers.
"""

import logging
from contextlib import nullcontext

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.monitoring.context import request_context

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for application-level errors."""

    def __init__(
        self,
        message: str,
        code: str = "app_error",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        #: Optional response headers — added for `LoginLockedError`'s own
        #: `Retry-After`, so a caller told to back off is also told for
        #: how long, not just that it must. `None` for every error that
        #: predates this and never needs one.
        self.headers = headers


def register_exception_handlers(app: FastAPI) -> None:
    """Register centralized exception handlers on the application."""

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "detail": exc.message},
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # This handler runs in Starlette's ServerErrorMiddleware, outside
        # every user middleware, so the request context is already unbound;
        # rebind it from the request so this log line carries the request
        # id, path, and user (see `app.monitoring.context`).
        log_context = getattr(request.state, "log_context", None)
        with request_context(log_context) if log_context is not None else nullcontext():
            logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "internal_error", "detail": "Internal server error"},
        )
