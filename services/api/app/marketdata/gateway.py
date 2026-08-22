"""Live market data streaming gateway.

Bridges the in-process event bus to browser WebSocket clients connected at
``/api/v1/ws/market`` (see :mod:`app.api.v1.endpoints.market_stream`). This
is the *only* real-time channel the dashboard uses — it relays events the
processing pipeline already published from the Delta WebSocket client (see
``app.runtime.Runtime``); the browser never talks to the exchange.

One :class:`MarketStreamGateway` is process-wide (owned by ``Runtime``,
like the event bus and state manager) and fans events out to every
connection subscribed to the affected symbol. Each connection gets its own
bounded outbound queue so one slow browser client can never block delivery
to the others, or block the event bus's publish path — a full queue drops
the message and counts it rather than backing up.

Order book messages are read from :class:`~app.marketdata.orderbook.OrderBookAggregator`,
not relayed straight from the bus event — a single ``OrderBookUpdated``
event can be an incremental diff of only a handful of changed price
levels, not something a browser could render as a coherent book on its
own. The aggregator does that reconstruction; this gateway just asks it
for the current top-of-book view on every update and on every new
subscription.
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from app.events.bus import EventBus
from app.events.event import Event
from app.marketdata.bus_events import OrderBookUpdated, TickerUpdated, TradeEventReceived
from app.marketdata.models import OrderBookLevel, TickerEvent, TradeEvent
from app.marketdata.orderbook import OrderBookAggregator, OrderBookSnapshot
from app.state.manager import MarketStateManager

__all__ = ["ConnectionHandle", "GatewayMetrics", "MarketStreamGateway"]

logger = logging.getLogger("app.marketdata.gateway")

Message = dict[str, object]

_DEFAULT_QUEUE_SIZE = 1000

#: Deepest book relayed to a browser connection — matches the largest depth
#: the frontend's depth selector offers (10/25/50/100), so the wire payload
#: never carries more than a client could ever choose to display.
_ORDERBOOK_DEPTH = 100


@dataclass
class GatewayMetrics:
    """Counters for the ``/system/metrics`` endpoint and tests."""

    connections_opened: int = 0
    connections_closed: int = 0
    messages_sent: int = 0
    messages_dropped: int = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "connections_opened": self.connections_opened,
            "connections_closed": self.connections_closed,
            "messages_sent": self.messages_sent,
            "messages_dropped": self.messages_dropped,
        }


class ConnectionHandle:
    """One browser connection: its subscriptions and outbound queue.

    The queue is bounded so a slow/stalled browser client cannot grow
    memory unboundedly or block the event bus's publish path — see
    :meth:`MarketStreamGateway._fanout`.
    """

    def __init__(self, queue_maxsize: int = _DEFAULT_QUEUE_SIZE) -> None:
        self.symbols: set[str] = set()
        self.queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=queue_maxsize)


class MarketStreamGateway:
    """Fans out live trade/ticker/order-book events to subscribed connections."""

    def __init__(
        self,
        state_manager: MarketStateManager,
        order_book: OrderBookAggregator | None = None,
        metrics: GatewayMetrics | None = None,
    ) -> None:
        self._state_manager = state_manager
        self._order_book = order_book
        self._connections: set[ConnectionHandle] = set()
        self._by_symbol: dict[str, set[ConnectionHandle]] = defaultdict(set)
        self.metrics = metrics if metrics is not None else GatewayMetrics()

    def attach(self, bus: EventBus) -> "MarketStreamGateway":
        """Subscribe the fan-out handlers to the live event types."""
        bus.subscribe("TradeEventReceived", self._on_trade)
        bus.subscribe("TickerUpdated", self._on_ticker)
        bus.subscribe("OrderBookUpdated", self._on_order_book)
        return self

    def connection_count(self) -> int:
        """Number of currently-registered browser connections."""
        return len(self._connections)

    def subscriber_count(self, symbol: str) -> int:
        """Number of connections subscribed to ``symbol``."""
        return len(self._by_symbol.get(symbol, ()))

    def register(self) -> ConnectionHandle:
        """Register a new connection; call :meth:`unregister` on close."""
        handle = ConnectionHandle()
        self._connections.add(handle)
        self.metrics.connections_opened += 1
        return handle

    def unregister(self, handle: ConnectionHandle) -> None:
        """Remove a connection and every subscription it held."""
        for symbol in list(handle.symbols):
            self._remove_subscriber(symbol, handle)
        self._connections.discard(handle)
        self.metrics.connections_closed += 1

    def subscribe(self, handle: ConnectionHandle, symbols: list[str]) -> None:
        """Subscribe ``handle`` to ``symbols`` and queue an immediate snapshot.

        The snapshot (current known trade/ticker, possibly both ``None``
        for a symbol with no data yet) lets a client render something
        before the next live event arrives, rather than showing a blank
        card indefinitely on a quiet market.
        """
        for raw_symbol in symbols:
            symbol = raw_symbol.strip().upper()
            if not symbol:
                continue
            handle.symbols.add(symbol)
            self._by_symbol[symbol].add(handle)
            self._enqueue(handle, self._snapshot_message(symbol))

    def unsubscribe(self, handle: ConnectionHandle, symbols: list[str]) -> None:
        """Unsubscribe ``handle`` from ``symbols``."""
        for raw_symbol in symbols:
            symbol = raw_symbol.strip().upper()
            handle.symbols.discard(symbol)
            self._remove_subscriber(symbol, handle)

    def _remove_subscriber(self, symbol: str, handle: ConnectionHandle) -> None:
        subscribers = self._by_symbol.get(symbol)
        if subscribers is None:
            return
        subscribers.discard(handle)
        if not subscribers:
            del self._by_symbol[symbol]

    def _snapshot_message(self, symbol: str) -> Message:
        state = self._state_manager.get_market_state(symbol)
        trade = state.trade if state is not None else None
        ticker = state.ticker if state is not None else None
        book = (
            self._order_book.get_book(symbol, depth=_ORDERBOOK_DEPTH) if self._order_book else None
        )
        return {
            "type": "snapshot",
            "symbol": symbol,
            "trade": _trade_payload(trade) if trade is not None else None,
            "ticker": _ticker_payload(ticker) if ticker is not None else None,
            "orderbook": _orderbook_payload(book) if book is not None else None,
        }

    async def _on_trade(self, event: Event) -> None:
        if not isinstance(event, TradeEventReceived):
            return
        trade = event.trade
        await self._fanout(
            trade.symbol,
            {"type": "trade", "symbol": trade.symbol, "data": _trade_payload(trade)},
        )

    async def _on_ticker(self, event: Event) -> None:
        if not isinstance(event, TickerUpdated):
            return
        ticker = event.ticker
        await self._fanout(
            ticker.symbol,
            {"type": "ticker", "symbol": ticker.symbol, "data": _ticker_payload(ticker)},
        )

    async def _on_order_book(self, event: Event) -> None:
        if not isinstance(event, OrderBookUpdated) or self._order_book is None:
            return
        symbol = event.order_book.symbol
        # Read the *reconstructed* book back out of the aggregator rather than
        # relaying this one raw event — a single incremental diff is only a
        # few changed levels, not something a browser client could render as
        # a coherent order book on its own (see `orderbook.py`).
        book = self._order_book.get_book(symbol, depth=_ORDERBOOK_DEPTH)
        if book is None:
            return
        await self._fanout(
            symbol,
            {"type": "orderbook", "symbol": symbol, "data": _orderbook_payload(book)},
        )

    async def _fanout(self, symbol: str, message: Message) -> None:
        for handle in list(self._by_symbol.get(symbol, ())):
            self._enqueue(handle, message)

    def _enqueue(self, handle: ConnectionHandle, message: Message) -> None:
        try:
            handle.queue.put_nowait(message)
            self.metrics.messages_sent += 1
            logger.debug(
                "Market stream message queued for connection (type=%s, symbol=%s)",
                message.get("type"),
                message.get("symbol"),
            )
        except asyncio.QueueFull:
            self.metrics.messages_dropped += 1
            logger.warning(
                "Dropped a market-stream message for a slow consumer (symbol=%s)",
                message.get("symbol"),
            )


def _trade_payload(trade: TradeEvent) -> dict[str, object]:
    return {
        "price": str(trade.price),
        "size": str(trade.size),
        "side": trade.side,
        "event_time": _isoformat_utc(trade.event_time),
    }


def _ticker_payload(ticker: TickerEvent) -> dict[str, object]:
    return {
        "last_price": _decimal_str(ticker.last_price),
        "bid": _decimal_str(ticker.bid),
        "ask": _decimal_str(ticker.ask),
        "mark_price": _decimal_str(ticker.mark_price),
        "price_change_24h": _decimal_str(ticker.price_change_24h),
        "event_time": _isoformat_utc(ticker.event_time),
    }


def _orderbook_payload(book: OrderBookSnapshot) -> dict[str, object]:
    return {
        "bids": [_level_payload(level) for level in book.bids],
        "asks": [_level_payload(level) for level in book.asks],
        "event_time": _isoformat_utc(book.event_time) if book.event_time is not None else None,
        "sequence": book.sequence,
    }


def _level_payload(level: OrderBookLevel) -> dict[str, object]:
    return {"price": str(level.price), "size": str(level.size)}


def _decimal_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _isoformat_utc(value: datetime) -> str:
    """ISO-8601 UTC with a ``Z`` suffix, matching the REST layer's own
    ``field_serializer`` convention (``app/schemas/market_data.py``).

    Plain ``datetime.isoformat()`` renders a UTC-aware datetime with a
    ``+00:00`` offset instead of ``Z``. The frontend's Zod schemas
    (``z.string().datetime()``) accept only the literal ``Z`` suffix by
    default, so a ``+00:00`` timestamp silently fails validation and the
    whole message is dropped — every trade/ticker/snapshot frame, in
    practice, while heartbeat pongs (which carry no timestamp) keep working
    and mask the failure as a live-looking connection with no data.
    """
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")
