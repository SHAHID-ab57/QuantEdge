"""Exception types for the External Data Connectors context.

Two families, deliberately kept apart:

- **Client-level** (`ConnectorError` and its subclasses) mirror
  `app.integrations.delta.exceptions`'s own hierarchy exactly —
  authentication, rate-limiting, API, and transport failures handled
  independently — so every future connector's own HTTP client can reuse
  the identical shape the Delta client already established, rather than
  inventing a second one per source.
- **Registry-level** (`ConnectorNotFoundError`, `DuplicateConnectorError`)
  mirror `app.features.errors`'s own `FeatureNotFoundError`/
  `DuplicateFeatureError` split: a lookup miss is a plain `RuntimeError`
  here (never an `AppError`) because nothing on this platform exposes a
  connector by name over HTTP yet — every caller today is internal
  (ingestion, a scheduler, a script), never an API request a client could
  trigger with a bad name.
"""

from typing import Any


class ConnectorError(Exception):
    """Base class for every external data connector client error."""

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


class ConnectorAuthenticationError(ConnectorError):
    """Authentication failed or credentials are missing.

    Fear & Greed itself never raises this (alternative.me's endpoint is
    free and unauthenticated) — declared here for the connectors this
    abstraction is built to support next (Marketaux, Etherscan, FRED),
    which do require credentials.
    """


class ConnectorRateLimitError(ConnectorError):
    """The source's rate limit was exceeded and retries were exhausted."""

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


class ConnectorAPIError(ConnectorError):
    """The source returned an error payload, or a malformed/unparseable response."""


class ConnectorNetworkError(ConnectorError):
    """A transport-level failure occurred (connect, timeout, protocol)."""


class ConnectorNotFoundError(RuntimeError):
    """Raised when the requested connector source is not in the registry.

    Not an `AppError`: every caller today is internal (a scheduler, a
    backfill script), never an HTTP request a client could trigger with
    an unknown source name.
    """

    def __init__(self, source: str, available: tuple[str, ...] = ()) -> None:
        suffix = f"; available: {', '.join(available)}" if available else ""
        super().__init__(f"Connector {source!r} is not registered{suffix}")
        self.source = source


class DuplicateConnectorError(RuntimeError):
    """Raised at import time when two connectors claim the same source name.

    A programming mistake caught once at startup, never a condition an
    HTTP request can trigger — the same posture
    `app.features.errors.DuplicateFeatureError` already takes for the
    identical situation in the feature registry.
    """

    def __init__(self, source: str) -> None:
        super().__init__(
            f"A connector for source {source!r} is already registered; "
            "connector sources must be unique across the registry"
        )
        self.source = source
