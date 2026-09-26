"""Per-request context shared by log lines and error-tracking events.

Held in one `contextvars` value, so each request (each asyncio task) sees
only its own. `JsonFormatter` reads it at format time, which means no
existing `logger.*` call needs to change to gain a request id or path.

The value is a plain dict that is *shared by reference* with the request's
ASGI scope (`scope["state"]["log_context"]`). That matters: the app's
catch-all exception handler runs in Starlette's `ServerErrorMiddleware`,
outside every user middleware, after the context variable has already been
reset. It can rebind the same dict from `request.state`, so the single most
important log line ("Unhandled exception") still carries the request id.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_context: ContextVar[dict[str, str] | None] = ContextVar("request_log_context", default=None)


@contextmanager
def request_context(info: dict[str, str]) -> Iterator[None]:
    """Bind `info` (request_id/method/path, plus user_id once known)."""
    token = _context.set(info)
    try:
        yield
    finally:
        _context.reset(token)


def set_user_id(user_id: str) -> None:
    """Record the authenticated user for the rest of this request.

    Mutates the shared dict, so it is visible to the exception handler
    that rebinds it after the request's own context has been reset.
    """
    info = _context.get()
    if info is not None:
        info["user_id"] = user_id


def current_context() -> dict[str, str]:
    """A copy of the current request context (empty outside a request)."""
    return dict(_context.get() or {})
