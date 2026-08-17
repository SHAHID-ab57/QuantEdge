"""In-process asynchronous event bus.

A lightweight, broker-free publish/subscribe bus for decoupling modules
within the service. Events are routed by ``event_type`` to registered
handlers. Publishing schedules one task per matching handler and returns
immediately; handlers run concurrently, are isolated from each other's
failures, and are timed for observability. No persistence, retries, or
backpressure — the abstraction is intentionally thin so a broker-backed
implementation (Kafka/RabbitMQ) can replace it later.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from app.events.event import Event

logger = logging.getLogger("app.events")

Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    """Routes events to handlers registered for the event ``type``.

    Use :meth:`subscribe` to register a handler, :meth:`publish` to
    dispatch an event, and :meth:`drain` to await all pending handler
    tasks (tests, shutdown). Handler exceptions are logged and never
    propagate to publishers or other handlers.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, set[Handler]] = {}
        self._pending: set[asyncio.Task[None]] = set()

    @property
    def pending_count(self) -> int:
        """Number of handler tasks currently running or queued."""
        return len(self._pending)

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register ``handler`` for events of type ``event_type``.

        Registering the same handler twice is a no-op.
        """
        if self._handlers.setdefault(event_type, set()).add(handler):
            logger.info(
                "Subscribed handler %r to %s (subscribers=%d)",
                handler,
                event_type,
                len(self._handlers[event_type]),
            )

    def unsubscribe(self, event_type: str, handler: Handler) -> bool:
        """Remove ``handler`` from one event type; True when removed."""
        handlers = self._handlers.get(event_type)
        if handlers is None or handler not in handlers:
            return False
        handlers.discard(handler)
        if not handlers:
            del self._handlers[event_type]
        else:
            logger.info(
                "Unsubscribed handler %r from %s (subscribers=%d)",
                handler,
                event_type,
                len(handlers),
            )
        return True

    def unsubscribe_all(self, handler: Handler) -> int:
        """Remove ``handler`` from every event type; returns count removed."""
        removed = 0
        for event_type in list(self._handlers):
            if self.unsubscribe(event_type, handler):
                removed += 1
        return removed

    def subscriber_count(self, event_type: str) -> int:
        """Number of handlers registered for an event type."""
        return len(self._handlers.get(event_type, ()))

    async def publish(self, event: Event) -> None:
        """Dispatch ``event`` to matching handlers without awaiting them.

        One task per handler is scheduled; use :meth:`drain` to wait for
        completion. A raising handler is logged and never affects the
        others.
        """
        handlers = list(self._handlers.get(event.event_type, ()))
        logger.debug(
            "Event published: type=%s id=%s source=%s subscribers=%d",
            event.event_type,
            event.event_id,
            event.source,
            len(handlers),
        )
        for handler in handlers:
            self._pending.add(asyncio.create_task(self._invoke(handler, event)))

    async def drain(self) -> None:
        """Wait until every scheduled handler task has completed.

        Handlers published during draining are included; this only
        returns once nothing is pending.
        """
        while self._pending:
            snapshot = list(self._pending)
            await asyncio.gather(*snapshot, return_exceptions=True)
            self._pending.difference_update(snapshot)

    async def _invoke(self, handler: Handler, event: Event) -> None:
        """Run one handler, timing it and isolating its failures."""
        start = time.perf_counter()
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "Event handler %r failed on %s (id=%s)",
                handler,
                event.event_type,
                event.event_id,
            )
        duration_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "Event handler %r completed: type=%s id=%s duration=%.2fms",
            handler,
            event.event_type,
            event.event_id,
            duration_ms,
        )