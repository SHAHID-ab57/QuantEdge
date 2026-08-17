"""Generic async WebSocket infrastructure.

Protocol-agnostic machinery shared by streaming integrations: connection
management with supervised reconnection, subscription tracking, typed
message parsing, and event dispatch. Delta Exchange protocol specifics
live in :mod:`app.integrations.delta.websocket`.
"""

from app.ws.config import WebSocketSettings
from app.ws.connection import ConnectionManager
from app.ws.dispatcher import EventDispatcher
from app.ws.exceptions import WebSocketError
from app.ws.models import UnknownWSEvent, WSEvent
from app.ws.parser import MessageParser, ParsedMessage
from app.ws.subscriptions import SubscriptionManager

__all__ = [
    "ConnectionManager",
    "EventDispatcher",
    "MessageParser",
    "ParsedMessage",
    "SubscriptionManager",
    "UnknownWSEvent",
    "WSEvent",
    "WebSocketError",
    "WebSocketSettings",
]
