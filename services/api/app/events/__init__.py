"""In-process asynchronous event bus for decoupled module communication.

Publish/subscribe with fire-and-forget async dispatch, error isolation,
and per-handler execution-time logging. No external broker; the thin
abstraction can be replaced by Kafka/RabbitMQ later.
"""

from app.events.bus import EventBus, Handler
from app.events.event import Event
from app.events.example_events import CandleClosed, MarketTradeReceived, OrderBookUpdated
from app.events.handlers import DebugHandler, LoggingHandler

__all__ = [
    "CandleClosed",
    "DebugHandler",
    "Event",
    "EventBus",
    "Handler",
    "LoggingHandler",
    "MarketTradeReceived",
    "OrderBookUpdated",
]