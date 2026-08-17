"""Example event handlers for the in-process event bus.

Handlers are plain async callables; classes exposing ``__call__`` are a
convenient way to keep handler state and configuration together. Instances
are passed directly to :meth:`EventBus.subscribe`.
"""

import logging

from app.events.event import Event

logger = logging.getLogger("app.events")


class LoggingHandler:
    """Log a one-line summary of every event received."""

    async def __call__(self, event: Event) -> None:
        logger.info(
            "Event received: type=%s id=%s source=%s timestamp=%s",
            event.event_type,
            event.event_id,
            event.source,
            event.timestamp.isoformat(),
        )


class DebugHandler:
    """Log the full payload of every event received at DEBUG level."""

    async def __call__(self, event: Event) -> None:
        logger.debug(
            "Event payload: type=%s id=%s payload=%s",
            event.event_type,
            event.event_id,
            event.payload,
        )