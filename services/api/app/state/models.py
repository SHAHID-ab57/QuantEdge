"""Snapshot model for the market state manager."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.events.example_events import CandleClosed
from app.marketdata.models import OrderBookEvent, TickerEvent, TradeEvent

__all__ = ["MarketState"]


@dataclass(frozen=True)
class MarketState:
    """Immutable view of the latest state for one symbol.

    Field values are the live domain objects held by the manager at
    snapshot time (dict reads are atomic on the event loop). Consumers
    must treat them as read-only.
    """

    symbol: str
    updated_at: datetime
    trade: TradeEvent | None = None
    ticker: TickerEvent | None = None
    candle: CandleClosed | None = None
    order_book: OrderBookEvent | None = None

    @property
    def last_price(self) -> Decimal | None:
        """Best available last price: trade, else ticker last/mark price."""
        if self.trade is not None:
            return self.trade.price
        if self.ticker is not None:
            if self.ticker.last_price is not None:
                return self.ticker.last_price
            return self.ticker.mark_price
        return None
