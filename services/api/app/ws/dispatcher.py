"""Fan out parsed events to registered async listeners."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.ws.models import WSEvent

logger = logging.getLogger("app.ws")

WILDCARD = "*"

Listener = Callable[[WSEvent], Awaitable[None]]


class EventDispatcher:
    """Routes events to listeners registered for the event ``type``.

    Listeners registered for ``"*"`` receive every event. Handlers run as
    separate tasks: a raising or slow listener never blocks the receive
    loop or the other listeners.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = {}

    def add_listener(self, channel: str, handler: Listener) -> None:
        """Register ``handler`` for events of type ``channel`` (``*`` = all)."""
        self._listeners.setdefault(channel, []).append(handler)

    def remove_listener(self, channel: str, handler: Listener) -> bool:
        """Remove a listener; returns True when one was removed."""
        handlers = self._listeners.get(channel)
        if not handlers:
            return False
        try:
            handlers.remove(handler)
        except ValueError:
            return False
        if not handlers:
            del self._listeners[channel]
        return True

    def emit(self, event: WSEvent) -> None:
        """Schedule every matching listener without awaiting them."""
        if not self._listeners:
            return
        handlers = [
            *self._listeners.get(event.type, ()),
            *self._listeners.get(WILDCARD, ()),
        ]
        loop = asyncio.get_running_loop()
        for handler in handlers:
            loop.create_task(self._invoke(handler, event))

    async def _invoke(self, handler: Listener, event: WSEvent) -> None:
        """Run one listener, isolating its failures from the stream."""
        try:
            await handler(event)
        except Exception:
            logger.exception("WebSocket listener %r failed on %s", handler, event.type)
