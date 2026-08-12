"""Exception types raised by the Delta Exchange client.

The hierarchy mirrors the failure modes of the HTTP layer so callers can
react to authentication, throttling, API, and transport problems
independently.
"""

from typing import Any


class DeltaError(Exception):
    """Base class for every Delta Exchange client error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


class AuthenticationError(DeltaError):
    """Authentication failed or credentials are missing."""


class RateLimitError(DeltaError):
    """The API rate limit was exceeded and retries were exhausted."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        status_code: int | None = None,
        detail: Any | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, detail=detail)
        self.retry_after = retry_after


class APIError(DeltaError):
    """The API returned an error payload or an unparseable response."""


class NetworkError(DeltaError):
    """A transport-level failure occurred (connect, timeout, protocol)."""
