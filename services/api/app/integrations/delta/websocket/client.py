"""Async WebSocket client for Delta Exchange streaming data.

Wires the generic connection machinery (:mod:`app.ws`) to the Delta
protocol: key-auth on every (re)connect to the private socket, heartbeat
and ping/pong supervision, subscription tracking with
resubscribe-on-reconnect, typed message parsing, and event dispatch to
listeners. Public channels use the public socket and need no
authentication. No persistence or business logic lives here.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from app.core.config import get_settings
from app.integrations.delta.exceptions import AuthenticationError
from app.integrations.delta.websocket import models as events
from app.integrations.delta.websocket.auth import sign_key_auth
from app.integrations.delta.websocket.parser import DeltaMessageParser
from app.ws.config import WebSocketSettings
from app.ws.connection import ConnectionManager
from app.ws.dispatcher import EventDispatcher
from app.ws.exceptions import WebSocketError
from app.ws.models import WSEvent
from app.ws.subscriptions import SubscriptionManager

logger = logging.getLogger("app.integrations.delta.websocket")

DEFAULT_AUTH_TIMEOUT = 10.0

Listener = Callable[[WSEvent], Awaitable[None]]


class DeltaWebSocketClient:
    """Streaming client for the Delta Exchange WebSocket API.

    Connect with :meth:`run` (or :meth:`start` for background use), close
    with :meth:`close`. Subscribe to channels with :meth:`subscribe` and
    consume typed events through listeners added with :meth:`add_listener`.
    On the private socket the client authenticates automatically after
    every (re)connect and re-requests tracked subscriptions, so listeners
    observe a seamless stream across connection drops.
    """

    def __init__(
        self,
        settings: WebSocketSettings,
        *,
        public: bool = True,
        api_key: str | None = None,
        api_secret: str | None = None,
        auth_timeout: float = DEFAULT_AUTH_TIMEOUT,
    ) -> None:
        """Initialize the client.

        Args:
            settings: Connection settings; ``url`` should point at the
                public socket for public channels or the private socket
                for private channels.
            public: True for the public endpoint (no authentication).
                False for the private endpoint, which requires
                ``api_key``/``api_secret`` and performs ``key-auth``.
            api_key: Delta API key used for ``key-auth``.
            api_secret: Delta API secret used for ``key-auth``.
            auth_timeout: Seconds to wait for the ``key-auth`` response.

        Raises:
            AuthenticationError: When the private endpoint is used
                without credentials, or the ``key-auth`` request is
                rejected.
        """
        if public:
            api_key = api_secret = None
        elif not api_key or not api_secret:
            raise AuthenticationError(
                "Delta API credentials required for the private WebSocket "
                "(set DELTA_API_KEY / DELTA_API_SECRET)"
            )
        if auth_timeout <= 0:
            raise ValueError("auth_timeout must be positive")
        self._public = public
        self._api_key = api_key
        self._api_secret = api_secret
        self._auth_timeout = auth_timeout
        self._parser = DeltaMessageParser()
        self._dispatcher = EventDispatcher()
        self._subscriptions = SubscriptionManager()
        self._auth_waiter: asyncio.Future[events.KeyAuthEvent] | None = None
        self._manager = ConnectionManager(
            settings,
            on_connected=self._on_connected,
            on_message=self._on_message,
            on_ping=self._on_ping,
        )

    @property
    def is_connected(self) -> bool:
        """True while the client connection is up and running."""
        return self._manager.is_connected

    @property
    def subscriptions(self) -> dict[str, list[str] | None]:
        """Snapshot of tracked subscriptions (symbols sorted)."""
        return self._subscriptions.requested

    async def run(self) -> None:
        """Run until shutdown or retries are exhausted."""
        await self._manager.run()

    def start(self) -> None:
        """Begin connecting in the background; returns immediately."""
        self._manager.start()

    async def close(self) -> None:
        """Gracefully close the connection and stop reconnection."""
        await self._manager.close()

    async def subscribe(
        self, channel: str, symbols: list[str] | None = None
    ) -> None:
        """Subscribe to a channel, optionally for specific symbols.

        When not yet connected, the subscription is queued and sent after
        the next (re)connect. Passing ``symbols=None`` subscribes to the
        whole channel.
        """
        payload = self._subscriptions.subscribe(channel, symbols)
        if payload is None:
            return
        if self.is_connected:
            try:
                await self._manager.send_text(payload)
                return
            except WebSocketError:
                logger.warning(
                    "WebSocket dropped while subscribing to %s; "
                    "will resubscribe on reconnect",
                    channel,
                )
        else:
            logger.info("WebSocket not connected; queued subscription to %s", channel)

    async def unsubscribe(
        self, channel: str, symbols: list[str] | None = None
    ) -> None:
        """Unsubscribe from a channel, optionally only for specific symbols."""
        payload = self._subscriptions.unsubscribe(channel, symbols)
        if payload is None:
            return
        if self.is_connected:
            try:
                await self._manager.send_text(payload)
            except WebSocketError:
                logger.warning(
                    "WebSocket dropped while unsubscribing from %s; "
                    "will not be re-requested",
                    channel,
                )

    def add_listener(self, channel: str, handler: Listener) -> None:
        """Register ``handler`` for events of type ``channel`` (``*`` = all)."""
        self._dispatcher.add_listener(channel, handler)

    def remove_listener(self, channel: str, handler: Listener) -> bool:
        """Remove a listener; returns True when one was removed."""
        return self._dispatcher.remove_listener(channel, handler)

    async def _on_connected(self) -> None:
        """First actions on every (re)connect: heartbeat, auth, resubscribe.

        The auth waiter must be registered before any await so the
        receive loop can resolve it no matter how quickly the server
        responds. Public endpoints skip ``key-auth`` entirely.
        """
        if not self._public:
            self._auth_waiter = asyncio.get_running_loop().create_future()
        await self._manager.send_json({"type": "enable_heartbeat"})
        if not self._public:
            try:
                await self._authenticate()
            except AuthenticationError as exc:
                logger.error("WebSocket authentication failed: %s", exc.message)
                await self._manager.abort("key-auth failed")
                return
        payload = self._subscriptions.resubscribe_payload()
        if payload is not None:
            logger.info(
                "WebSocket resubscribing to %d channel(s)",
                len(self._subscriptions.requested),
            )
            await self._manager.send_text(payload)

    async def _on_ping(self) -> None:
        """Send a protocol ping when the connection supervisor asks."""
        await self._manager.send_json({"type": "ping"})

    async def _authenticate(self) -> None:
        """Send ``key-auth`` and wait for the server response."""
        waiter = self._auth_waiter
        assert waiter is not None
        assert self._api_secret is not None
        timestamp = str(int(time.time()))
        await self._manager.send_json(
            {
                "type": "key-auth",
                "payload": {
                    "api-key": self._api_key,
                    "signature": sign_key_auth(self._api_secret, timestamp),
                    "timestamp": timestamp,
                },
            }
        )
        try:
            response = await asyncio.wait_for(waiter, timeout=self._auth_timeout)
        except TimeoutError:
            raise AuthenticationError("WebSocket key-auth timed out") from None
        if not response.success:
            raise AuthenticationError(
                f"WebSocket key-auth failed: {response.status} "
                f"({response.status_code})"
            )
        logger.info("WebSocket authenticated")

    async def _on_message(self, raw: str) -> None:
        """Parse one frame and route it to supervisors, ack handlers, or listeners."""
        parsed = self._parser.parse(raw)
        if parsed.error is not None:
            logger.warning("WebSocket message rejected: %s", parsed.error)
            return
        event = parsed.event
        if event is None:
            return
        if isinstance(event, events.HeartbeatEvent):
            self._manager.notify_heartbeat()
            logger.debug("WebSocket heartbeat received")
            return
        if isinstance(event, events.PongEvent):
            self._manager.notify_pong()
            logger.debug("WebSocket pong received")
            return
        if isinstance(event, events.KeyAuthEvent):
            waiter = self._auth_waiter
            if waiter is not None and not waiter.done():
                waiter.set_result(event)
            return
        if isinstance(event, events.SubscriptionsEvent):
            errors = self._subscriptions.handle_ack(
                [channel.model_dump() for channel in event.channels]
            )
            logger.info(
                "WebSocket subscriptions active: %s",
                [channel.name for channel in event.channels],
            )
            for error in errors:
                logger.error("WebSocket subscription rejected: %s", error)
            return
        logger.debug("WebSocket event: %s", event.type)
        self._dispatcher.emit(event)


def get_delta_ws_client(
    settings: WebSocketSettings | None = None,
    *,
    public: bool = True,
) -> DeltaWebSocketClient:
    """Return a Delta WebSocket client configured from application settings.

    Public mode (default) reads ``DELTA_WS_URL`` (the public socket by
    default) and needs no credentials. Private mode reads
    ``DELTA_WS_PRIVATE_URL`` and requires ``DELTA_API_KEY`` /
    ``DELTA_API_SECRET``. Reconnect behavior comes from
    ``DELTA_WS_RECONNECT_DELAY`` and ``DELTA_WS_MAX_RETRIES``.
    """
    app_settings = get_settings()
    url = app_settings.delta_ws_url if public else app_settings.delta_ws_private_url
    return DeltaWebSocketClient(
        settings
        or WebSocketSettings(
            url=url,
            reconnect_delay=app_settings.delta_ws_reconnect_delay,
            max_retries=app_settings.delta_ws_max_retries,
        ),
        public=public,
        api_key=app_settings.delta_api_key,
        api_secret=app_settings.delta_api_secret,
    )
