"""Exchange-independent market data domain models.

These models are the only market data shape the rest of the application
may consume. Exchange-specific wire formats (Delta compact keys,
microsecond timestamps) are converted by normalizers and never leak past
:mod:`app.marketdata.normalizer`.

Prices and sizes are validated at construction: negative or zero prices
are rejected, sizes may be zero (an order book level with ``0`` size
means "remove this price level"). Timestamps must be timezone-aware.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SYMBOL_PATTERN = r"^[A-Z0-9_.:\-+]+$"

__all__ = [
    "FundingRateEvent",
    "MarketDataEvent",
    "OrderBookEvent",
    "OrderBookLevel",
    "SYMBOL_PATTERN",
    "TickerEvent",
    "TradeEvent",
]


class MarketDataEvent(BaseModel):
    """Base class for every normalized market data event.

    ``event_time`` is the exchange-assigned timestamp (UTC).
    ``received_time`` is when the message was normalized (UTC, defaults
    to now). ``sequence`` is the exchange sequence number when the feed
    provides one, otherwise ``None``.
    """

    model_config = {"extra": "forbid"}

    exchange: str = Field(min_length=1)
    symbol: str = Field(min_length=1, pattern=SYMBOL_PATTERN)
    event_time: datetime
    received_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sequence: int | None = None

    @model_validator(mode="after")
    def _timestamps_must_be_utc(self) -> "MarketDataEvent":
        for name in ("event_time", "received_time"):
            value = getattr(self, name)
            if value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware (UTC)")
        return self


class TradeEvent(MarketDataEvent):
    """A single market trade fill."""

    side: Literal["buy", "sell", "bid", "ask", "unknown"]
    price: Decimal = Field(gt=0)
    size: Decimal = Field(gt=0)
    trade_time: datetime | None = None


class TickerEvent(MarketDataEvent):
    """A per-symbol ticker update (top of book + 24h summary)."""

    bid: Decimal | None = Field(default=None, ge=0)
    ask: Decimal | None = Field(default=None, ge=0)
    bid_size: Decimal | None = Field(default=None, ge=0)
    ask_size: Decimal | None = Field(default=None, ge=0)
    last_price: Decimal | None = Field(default=None, ge=0)
    mark_price: Decimal | None = Field(default=None, ge=0)
    spot_price: Decimal | None = Field(default=None, ge=0)
    open_interest: Decimal | None = Field(default=None, ge=0)
    price_change_24h: Decimal | None = None
    turnover: Decimal | None = Field(default=None, ge=0)


class FundingRateEvent(MarketDataEvent):
    """A perpetual-contract funding rate update.

    Arrives on its own channel, not the ticker — hence a separate domain
    event rather than a field on :class:`TickerEvent`. ``funding_rate`` is
    a signed fraction per funding interval (e.g. ``-0.0002`` = the shorts
    pay the longs 0.02% this interval); it is deliberately unconstrained in
    sign.
    """

    funding_rate: Decimal
    funding_interval_seconds: int | None = Field(default=None, gt=0)
    next_funding_time: datetime | None = None

    @model_validator(mode="after")
    def _next_funding_time_must_be_utc(self) -> "FundingRateEvent":
        if self.next_funding_time is not None and self.next_funding_time.tzinfo is None:
            raise ValueError("next_funding_time must be timezone-aware (UTC)")
        return self


class OrderBookLevel(BaseModel):
    """One price level of an order book."""

    model_config = {"extra": "forbid"}

    price: Decimal = Field(gt=0)
    size: Decimal = Field(ge=0)


class OrderBookEvent(MarketDataEvent):
    """An order book snapshot or update.

    ``bids`` and ``asks`` are sorted by the exchange convention: bids
    descending, asks ascending. ``is_snapshot`` is ``True`` for full
    snapshots (ob_l1/ob_l2 always; ob_updates only on the first frame).
    """

    kind: Literal["l1", "l2", "full"]
    bids: list[OrderBookLevel] = Field(default_factory=lambda: [])
    asks: list[OrderBookLevel] = Field(default_factory=lambda: [])
    is_snapshot: bool = True
