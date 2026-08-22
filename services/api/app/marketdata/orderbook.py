"""Reconstructs a coherent per-symbol L2 order book from the event bus.

:class:`~app.state.manager.MarketStateManager` deliberately does **not**
do this — its own docstring says order book reconstruction is "a consumer
concern," and it stores whatever `OrderBookEvent` arrived last, verbatim.
That is fine for trades/tickers (each message is a complete, independent
fact), but an order book is not: Delta's ``ob_updates`` channel sends one
full snapshot (``action="snapshot"``) followed by a stream of incremental
diffs (``action="update"``) that each carry only the *changed* price
levels — a level with ``size=0`` means "remove this level," not "size is
now zero." Storing the latest message verbatim, as the state manager does,
would replace the whole book with just the handful of levels in the most
recent diff on every tick.

This module is the missing "consumer": :class:`OrderBookAggregator`
subscribes to the same ``OrderBookUpdated`` bus event and maintains a full
per-symbol book by replacing on a snapshot and merging (upsert non-zero
sizes, drop zero-size levels) on an update.

``ob_l1`` events (``OrderBookEvent.kind == "l1"``) are deliberately
ignored here. They carry only the best bid/ask (one level per side) but
arrive as `is_snapshot=True` several times a second — if merged the same
way, each one would wipe the reconstructed depth book down to one level
per side. The ``ob_updates`` stream's own snapshot+diffs already include
the best bid/ask at the edges of the book, so ``ob_l1`` adds no
information this module needs.

Known limitation (documented, not fixed here): reconstruction trusts
stream order and does not validate Delta's per-message sequence number or
checksum, so a dropped message *within* a connected session could leave
the local book silently inconsistent until the next snapshot. A dropped
connection self-heals: the Delta client's resubscribe-on-reconnect always
provokes a fresh ``action="snapshot"``.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.events.bus import EventBus
from app.events.event import Event
from app.marketdata.bus_events import OrderBookUpdated
from app.marketdata.models import OrderBookLevel

__all__ = ["OrderBookAggregator", "OrderBookSnapshot"]

logger = logging.getLogger("app.marketdata.orderbook")

#: Kinds that represent genuine full-depth book state. ``l1`` is excluded —
#: see the module docstring.
_DEPTH_KINDS = frozenset({"l2", "full"})


@dataclass(frozen=True)
class OrderBookSnapshot:
    """A depth-limited, sorted read of one symbol's reconstructed book."""

    symbol: str
    bids: list[OrderBookLevel] = field(default_factory=list)  # descending by price
    asks: list[OrderBookLevel] = field(default_factory=list)  # ascending by price
    event_time: datetime | None = None
    sequence: int | None = None


class OrderBookAggregator:
    """Maintains a full per-symbol L2 book from snapshot + incremental diffs."""

    def __init__(self) -> None:
        self._bids: dict[str, dict[Decimal, Decimal]] = defaultdict(dict)
        self._asks: dict[str, dict[Decimal, Decimal]] = defaultdict(dict)
        self._event_time: dict[str, datetime] = {}
        self._sequence: dict[str, int | None] = {}

    def attach(self, bus: EventBus) -> "OrderBookAggregator":
        """Subscribe the reconstruction handler to the live event bus."""
        bus.subscribe("OrderBookUpdated", self._on_order_book)
        return self

    def has_book(self, symbol: str) -> bool:
        """True once at least one snapshot has been reconstructed for ``symbol``."""
        return symbol in self._event_time

    def get_book(self, symbol: str, depth: int | None = None) -> OrderBookSnapshot | None:
        """The current book for ``symbol``, sorted and optionally depth-limited.

        Returns ``None`` if no snapshot has been reconstructed yet (never an
        empty-but-present book — an empty book is a valid, sorted result with
        zero levels on one or both sides, which is different from "unknown").
        """
        if not self.has_book(symbol):
            return None
        bids = sorted(self._bids[symbol].items(), key=lambda item: item[0], reverse=True)
        asks = sorted(self._asks[symbol].items(), key=lambda item: item[0])
        if depth is not None:
            bids = bids[:depth]
            asks = asks[:depth]
        return OrderBookSnapshot(
            symbol=symbol,
            bids=[OrderBookLevel(price=price, size=size) for price, size in bids],
            asks=[OrderBookLevel(price=price, size=size) for price, size in asks],
            event_time=self._event_time.get(symbol),
            sequence=self._sequence.get(symbol),
        )

    async def _on_order_book(self, event: Event) -> None:
        if not isinstance(event, OrderBookUpdated):
            return
        book = event.order_book
        if book.kind not in _DEPTH_KINDS:
            return

        if book.is_snapshot:
            self._bids[book.symbol] = _index(book.bids)
            self._asks[book.symbol] = _index(book.asks)
        else:
            _merge(self._bids[book.symbol], book.bids)
            _merge(self._asks[book.symbol], book.asks)

        self._event_time[book.symbol] = book.event_time
        self._sequence[book.symbol] = book.sequence
        logger.debug(
            "Order book %s for %s (bids=%d, asks=%d)",
            "replaced" if book.is_snapshot else "merged",
            book.symbol,
            len(self._bids[book.symbol]),
            len(self._asks[book.symbol]),
        )


def _index(levels: list[OrderBookLevel]) -> dict[Decimal, Decimal]:
    return {level.price: level.size for level in levels}


def _merge(side: dict[Decimal, Decimal], levels: list[OrderBookLevel]) -> None:
    for level in levels:
        if level.size == 0:
            side.pop(level.price, None)
        else:
            side[level.price] = level.size
