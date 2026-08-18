"""Example domain events to guide Event Bus consumers.

These show the expected shape for the platform's core flows. Market data
events (trades, tickers, order books) now live in
:mod:`app.marketdata.bus_events`; this module keeps a candle example for
the future candle aggregation pipeline. Events carry typed fields (with
``payload`` auto-populated from them) and no business logic.
"""

from decimal import Decimal

from app.events.event import Event


class CandleClosed(Event):
    """A completed OHLC candle for a market and resolution."""

    symbol: str
    resolution: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal