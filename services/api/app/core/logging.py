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
    _configured = True
