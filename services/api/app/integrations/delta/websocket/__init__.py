"""Delta Exchange WebSocket protocol.

Typed message models, key-auth signing, a preloaded message parser, and
the streaming client built on the generic :mod:`app.ws` machinery.
"""

from app.integrations.delta.websocket import models as events
from app.integrations.delta.websocket.auth import sign_key_auth
from app.integrations.delta.websocket.client import (
    DEFAULT_AUTH_TIMEOUT,
    DeltaWebSocketClient,
    get_delta_ws_client,
)
from app.integrations.delta.websocket.parser import DeltaMessageParser

__all__ = [
    "DEFAULT_AUTH_TIMEOUT",
    "DeltaMessageParser",
    "DeltaWebSocketClient",
    "events",
    "get_delta_ws_client",
    "sign_key_auth",
]
