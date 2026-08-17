"""Example domain events to guide Event Bus consumers.

These show the expected shape for the platform's core flows — market data
ingestion, candles, and order books. They carry typed fields (with
``payload`` auto-populated from them) and no business logic.
"""

from decimal import Decimal

from app.events.event import Event


class MarketTradeReceived(Event):
    """A market trade observed on an exchange feed."""

    symbol: str
    price: Decimal
    size: Decimal
    side: str


class CandleClosed(Event):
    """A completed OHLC candle for a market and resolution."""

    symbol: str
    resolution: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class OrderBookUpdated(Event):
    """An order book snapshot or update for a symbol.

    ``asks`` and ``bids`` hold ``[price, size]`` pairs, asks ascending
    and bids descending.
    """

    symbol: str
    asks: list[tuple[Decimal, Decimal]]
    bids: list[tuple[Decimal, Decimal]]