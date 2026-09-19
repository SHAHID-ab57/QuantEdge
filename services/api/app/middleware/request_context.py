"""Bind a per-request id, method and path for logs and error events.

A pure ASGI middleware, not `BaseHTTPMiddleware`: the latter runs the
downstream app in a separate task, which does not reliably carry
`contextvars` values set here into the request handler (and so into its
log lines).
"""

import uuid

from starlette.types import ASGIApp, Receive, Scope, Send

from app.monitoring.context import request_context
from app.monitoring.error_tracking import tag_request


class RequestContextMiddleware:
    """Give every HTTP request a fresh id and expose it to log/event context."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        info = {"request_id": request_id, "method": scope["method"], "path": scope["path"]}
        # On the scope too, so the catch-all exception handler (which runs
        # outside this middleware) can rebind it: see `app.monitoring.context`.
        scope.setdefault("state", {})["log_context"] = info
        # A tag, so an error event found in the tracker can be matched to
        # the exact log lines of the same request (and vice versa).
        tag_request(request_id)
        with request_context(info):
            await self.app(scope, receive, send)
