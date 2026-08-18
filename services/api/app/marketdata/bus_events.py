"""Bus event wrappers for normalized market data.

The domain models in :mod:`app.marketdata.models` stay free of bus
coupling; these thin wrappers carry them onto the in-process event bus.
Subscribe with the wrapper's ``event_type`` (its class name):
``TradeEventReceived``, ``TickerUpdated``, ``OrderBookUpdated``.
"""

from app.events.event import Event
from app.marketdata.models import OrderBookEvent, TickerEvent, TradeEvent

__all__ = ["OrderBookUpdated", "TickerUpdated", "TradeEventReceived"]


class TradeEventReceived(Event):
    """A normalized market trade published on the event bus."""

    trade: TradeEvent


class TickerUpdated(Event):
    """A normalized per-symbol ticker published on the event bus."""

    ticker: TickerEvent


class OrderBookUpdated(Event):
    """A normalized order book snapshot/update published on the event bus."""

    order_book: OrderBookEvent