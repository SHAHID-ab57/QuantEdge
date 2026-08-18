"""Normalize exchange-specific messages into domain models.

The :class:`Normalizer` protocol is the extension point for future
exchanges: implement ``normalize`` and feed the result into the
pipeline. :class:`DeltaNormalizer` maps parsed Delta Exchange events
(:mod:`app.integrations.delta.websocket.models`) to the
exchange-independent models in :mod:`app.marketdata.models`.

Control and system messages (heartbeat, subscriptions, system status,
product updates) are recognized but produce no domain events
(``ignored``). Well-formed messages of types the normalizer does not map
(e.g. ``mark_price``, ``candlestick_*``, private account channels) are
reported as ``unsupported`` so the pipeline can count them.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Protocol

from app.integrations.delta.websocket.models import (
    HeartbeatEvent,
    KeyAuthEvent,
    OrderBookL1Event,
    OrderBookL2Event,
    OrderBookUpdatesEvent,
    PongEvent,
    ProductUpdatesEvent,
    SubscriptionsEvent,
    SystemStatusEvent,
    TickerData,
    TradesEvent,
    utc_from_micros,
)
from app.integrations.delta.websocket.models import (
    TickerEvent as DeltaTickerEvent,
)
from app.marketdata.models import (
    MarketDataEvent,
    OrderBookEvent,
    OrderBookLevel,
    TickerEvent,
    TradeEvent,
)
from app.ws.models import WSEvent

__all__ = [
    "DeltaNormalizer",
    "NormalizationResult",
    "Normalizer",
]

_IGNORED_TYPES = (
    HeartbeatEvent,
    KeyAuthEvent,
    PongEvent,
    SubscriptionsEvent,
    SystemStatusEvent,
    ProductUpdatesEvent,
)


@dataclass(frozen=True)
class NormalizationResult:
    """Outcome of normalizing one message.

    ``status`` is ``normalized`` when at least one domain event was
    produced, ``ignored`` for recognized control/system messages, and
    ``unsupported`` for well-formed messages of unhandled types.
    """

    events: tuple[MarketDataEvent, ...] = ()
    status: Literal["normalized", "ignored", "unsupported"] = "ignored"


class Normalizer(Protocol):
    """Exchange adapter: parsed WebSocket message in, domain events out."""

    def normalize(self, message: WSEvent) -> NormalizationResult:
        """Convert one parsed message to domain events (possibly none)."""
        ...


class DeltaNormalizer:
    """Maps parsed Delta WebSocket messages to domain models."""

    def __init__(self, exchange: str = "delta") -> None:
        self._exchange = exchange

    def normalize(self, message: WSEvent) -> NormalizationResult:
        if isinstance(message, TradesEvent):
            return NormalizationResult(
                events=(self._trade(message),), status="normalized"
            )
        if isinstance(message, DeltaTickerEvent):
            return NormalizationResult(
                events=self._tickers(message), status="normalized"
            )
        if isinstance(message, OrderBookL1Event):
            return NormalizationResult(
                events=(self._order_book_l1(message),), status="normalized"
            )
        if isinstance(message, OrderBookL2Event):
            return NormalizationResult(
                events=(self._order_book_l2(message),), status="normalized"
            )
        if isinstance(message, OrderBookUpdatesEvent):
            return NormalizationResult(
                events=(self._order_book_updates(message),), status="normalized"
            )
        if isinstance(message, _IGNORED_TYPES):
            return NormalizationResult()
        return NormalizationResult(status="unsupported")

    def _trade(self, message: TradesEvent) -> TradeEvent:
        return TradeEvent(
            exchange=self._exchange,
            symbol=message.sy,
            event_time=utc_from_micros(message.ts),
            trade_time=utc_from_micros(message.t),
            side="unknown",
            price=message.p,
            size=message.s,
        )

    def _tickers(self, message: DeltaTickerEvent) -> tuple[TickerEvent, ...]:
        if message.d is not None:
            return tuple(
                self._ticker_from_data(entry, frame_ts=message.ts)
                for entry in message.d
            )
        if message.sy is not None and message.ts is not None:
            return (
                TickerEvent(
                    exchange=self._exchange,
                    symbol=message.sy,
                    event_time=utc_from_micros(message.ts),
                    spot_price=message.sp,
                ),
            )
        return ()

    def _ticker_from_data(
        self, data: TickerData, *, frame_ts: int | None
    ) -> TickerEvent:
        quote = data.q or []
        ask = _at(quote, 0)
        ask_size = _at(quote, 1)
        bid = _at(quote, 2)
        bid_size = _at(quote, 3)
        ohlc = data.ohlc or []
        oi = data.oi or []
        turnover = data.to or []
        return TickerEvent(
            exchange=self._exchange,
            symbol=data.s,
            event_time=(
                utc_from_micros(frame_ts)
                if frame_ts is not None
                else datetime.now(UTC)
            ),
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            last_price=_at(ohlc, 3),
            mark_price=data.m,
            open_interest=_at(oi, 0),
            price_change_24h=data.m24hc,
            turnover=_at(turnover, 0),
        )

    def _order_book_l1(self, message: OrderBookL1Event) -> OrderBookEvent:
        return OrderBookEvent(
            exchange=self._exchange,
            symbol=message.sy,
            event_time=utc_from_micros(message.ts),
            kind="l1",
            bids=[OrderBookLevel(price=message.bp, size=message.bid_size)],
            asks=[OrderBookLevel(price=message.ap, size=message.ask_size)],
            is_snapshot=True,
        )

    def _order_book_l2(self, message: OrderBookL2Event) -> OrderBookEvent:
        return OrderBookEvent(
            exchange=self._exchange,
            symbol=message.sy,
            event_time=utc_from_micros(message.ts),
            kind="l2",
            bids=_levels(message.b),
            asks=_levels(message.a),
            is_snapshot=True,
        )

    def _order_book_updates(self, message: OrderBookUpdatesEvent) -> OrderBookEvent:
        return OrderBookEvent(
            exchange=self._exchange,
            symbol=message.sy,
            event_time=utc_from_micros(message.ts),
            sequence=message.seq,
            kind="full",
            bids=_levels(message.b),
            asks=_levels(message.a),
            is_snapshot=message.action == "snapshot",
        )


def _levels(levels: list[list[Decimal]] | None) -> list[OrderBookLevel]:
    if not levels:
        return []
    return [OrderBookLevel(price=level[0], size=level[1]) for level in levels]


def _at(values: Sequence[Decimal | None] | None, index: int) -> Decimal | None:
    if not values or len(values) <= index:
        return None
    return values[index]