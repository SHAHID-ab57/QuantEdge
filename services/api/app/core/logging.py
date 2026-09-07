"""Logging configuration placeholder.

Structured logging setup is applied at application startup.
"""

import logging

from app.core.config import get_settings

_configured = False


def setup_logging() -> None:
    """Configure the root logger for the service."""
    global _configured

    if _configured:
        return

    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
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
    _configured = True
