"""Logging configuration: structured JSON by default (M5-E5-T2).

Applied at application startup. `LOG_FORMAT=text` restores the old
human-readable line for reading a local dev console.
"""

import logging
import sys
from typing import IO, Literal

from app.core.config import get_settings
from app.monitoring.json_logging import JsonFormatter

_configured = False

#: Marks the handler this module installs, so it is added once and can be
#: found again (tests reconfigure it; pytest's own handlers are left alone).
_HANDLER_ATTR = "_app_log_handler"

_TEXT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

#: uvicorn configures these three with their own plain-text handlers and
#: `propagate=False`. Left alone, its lines would be plain text interleaved
#: with this app's JSON lines, which breaks every parser reading the stream.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def configure_logging(
    *,
    level: str,
    log_format: Literal["json", "text"],
    stream: IO[str] | None = None,
) -> logging.Handler:
    """Install (or replace) this app's single root log handler and return it."""
    root = logging.getLogger()
    for existing in [h for h in root.handlers if getattr(h, _HANDLER_ATTR, False)]:
        root.removeHandler(existing)

    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(
        JsonFormatter() if log_format == "json" else logging.Formatter(_TEXT_FORMAT)
    )
    setattr(handler, _HANDLER_ATTR, True)
    root.addHandler(handler)
    root.setLevel(level.upper())

    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True

    # httpx's own request logger logs the full request URL at INFO level,
    # including any query-string parameter — several connectors here
    # (Etherscan, FRED, Marketaux) send their real API key as a query
    # parameter (`apikey`/`api_key`/`api_token`), so at the root level
    # this configures, that line would log the real secret in cleartext
    # on every request. Each connector already logs its own safe
    # method/endpoint/status/duration line; httpx's own duplicate is
    # silenced rather than redacted, since httpx itself has no redaction
    # hook to filter just the secret out of the URL it logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return handler


def setup_logging() -> None:
    """Configure the root logger for the service (once per process)."""
    global _configured

    if _configured:
        return

    settings = get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    _configured = True
