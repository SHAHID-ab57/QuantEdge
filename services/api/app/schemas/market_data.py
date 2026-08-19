"""Response schemas (DTOs) for the market data API.

ORM models are never exposed directly; every response is built from these
Pydantic v2 models. Decimals serialize as JSON strings (lossless) and
datetimes as ISO-8601 UTC.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class MarketDTO(BaseModel):
    """A tradeable instrument on an exchange."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    exchange: str
    base_asset: str
    quote_asset: str
    market_type: str
    is_active: bool

    @field_validator("exchange", mode="before")
    @classmethod
    def _exchange_name(cls, value: object) -> object:
        """Extract the exchange name from the ORM relationship."""
        return getattr(value, "name", value)


class MarketListResponse(BaseModel):
    """All available markets."""

    markets: list[MarketDTO]
    total: int = Field(..., description="Number of markets returned")


class TimeframesResponse(BaseModel):
    """Timeframes that have stored candle data for one market."""

    symbol: str
    timeframes: list[str]


class CandleDTO(BaseModel):
    """One OHLCV candle."""

    model_config = ConfigDict(from_attributes=True)

    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal | None = None
    trade_count: int | None = None
    source: str

    @field_validator("open_time", "close_time", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        """Normalize timestamps to aware UTC for a stable JSON contract."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_serializer("open", "high", "low", "close", "volume", "quote_volume")
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        """Serialize decimals as plain strings without trailing zeros.

        Database scale (38, 18) would otherwise leak into the JSON contract
        (e.g. ``3050.500000000000000000``).
        """
        if value is None:
            return None
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text


class Pagination(BaseModel):
    """Pagination metadata for candle pages."""

    total: int = Field(..., description="Total candles matching the query")
    returned: int = Field(..., description="Candles returned in this page")
    has_more: bool = Field(..., description="Whether further pages exist")
    limit: int
    offset: int


class CandlePageResponse(BaseModel):
    """A page of candles, sorted ascending by open time."""

    symbol: str
    timeframe: str
    items: list[CandleDTO]
    pagination: Pagination


class LatestCandleResponse(BaseModel):
    """The most recent candle for a market/timeframe."""

    symbol: str
    timeframe: str
    candle: CandleDTO