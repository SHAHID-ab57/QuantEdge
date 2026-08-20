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
    exchange_id: uuid.UUID
    base_asset: str
    quote_asset: str
    market_type: str
    is_active: bool
    delta_product_id: int | None = None
    delta_contract_type: str | None = None
    tick_size: str | None = None
    funding_method: str | None = None
    funding_interval_seconds: int | None = None
    listing_date: datetime | None = None

    @field_validator("exchange", mode="before")
    @classmethod
    def _exchange_name(cls, value: object) -> object:
        """Extract the exchange name from the ORM relationship."""
        return getattr(value, "name", value)

    @field_validator("listing_date", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime | None) -> datetime | None:
        """Normalize datetimes to aware UTC for a stable JSON contract."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class MarketListResponse(BaseModel):
    """All available markets."""

    markets: list[MarketDTO]
    total: int = Field(..., description="Number of markets returned")


class TimeframesResponse(BaseModel):
    """Timeframes that have stored candle data for one market."""

    symbol: str
    timeframes: list[str]


class ResearchTimeframeMetrics(BaseModel):
    """Data-coverage research metrics for one market/timeframe."""

    timeframe: str
    stored_candles: int
    oldest_at: datetime | None = None
    newest_at: datetime | None = None
    coverage_days: float | None = None
    expected_candles: int
    missing_candles: int
    completeness: float | None = None
    average_daily_candles: float | None = None

    @field_validator("oldest_at", "newest_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime | None) -> datetime | None:
        """Normalize datetimes to aware UTC for a stable JSON contract."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class MarketResearchResponse(BaseModel):
    """Research metrics describing stored candle coverage for a market."""

    symbol: str
    oldest_candle_at: datetime | None = None
    newest_candle_at: datetime | None = None
    coverage_days: float | None = None
    total_candles: int
    timeframes: list[ResearchTimeframeMetrics]

    @field_validator("oldest_candle_at", "newest_candle_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime | None) -> datetime | None:
        """Normalize datetimes to aware UTC for a stable JSON contract."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


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
    """A page of candles with backend-computed analytics.

    ``statistics`` and ``quality`` describe the full query range ``[start, end)``
    (not just the returned page); ``meta`` reports server-side timing and
    execution metadata.
    """

    symbol: str
    timeframe: str
    items: list[CandleDTO]
    pagination: Pagination
    statistics: "CandleStatistics"
    quality: "CandleQuality"
    meta: "QueryMetadata"


class CandleStatistics(BaseModel):
    """Aggregate statistics for candles in the query range.

    Computed server-side from a single SQL aggregate over the range; the
    frontend never derives these values.
    """

    highest_price: Decimal | None
    lowest_price: Decimal | None
    highest_volume: Decimal | None
    lowest_volume: Decimal | None
    average_open: Decimal | None
    average_close: Decimal | None
    average_high: Decimal | None
    average_low: Decimal | None
    average_volume: Decimal | None
    total_candles: int
    first_candle_at: datetime | None = None
    last_candle_at: datetime | None = None
    expected_candles: int
    missing_candles: int
    completeness: float | None = None

    @field_serializer(
        "highest_price",
        "lowest_price",
        "highest_volume",
        "lowest_volume",
        "average_open",
        "average_close",
        "average_high",
        "average_low",
        "average_volume",
    )
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        """Serialize decimals as plain strings without trailing zeros."""
        if value is None:
            return None
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text

    @field_validator("first_candle_at", "last_candle_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime | None) -> datetime | None:
        """Normalize datetimes to aware UTC for a stable JSON contract."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class CandleQuality(BaseModel):
    """Backend-generated data quality metrics for the query range.

    Counts are exact; ``missing_intervals`` samples the earliest missing
    buckets (capped) so large ranges stay cheap to serve.
    """

    completeness_score: float
    freshness_score: float
    missing_interval_count: int
    missing_intervals: list[datetime] = []
    duplicate_candles: int
    out_of_order_candles: int
    invalid_ohlc_candles: int
    gaps_detected: bool
    overall_quality_score: float

    @field_validator("missing_intervals", mode="before")
    @classmethod
    def _ensure_utc_list(cls, value: list[datetime] | None) -> list[datetime]:
        """Normalize datetimes to aware UTC for a stable JSON contract."""
        if value is None:
            return []
        normalized: list[datetime] = []
        for item in value:
            if item.tzinfo is None:
                normalized.append(item.replace(tzinfo=UTC))
            else:
                normalized.append(item.astimezone(UTC))
        return normalized


class QueryMetadata(BaseModel):
    """Server-side execution metadata for one candle query.

    ``rows_scanned`` counts the ordered rows walked to reach the page
    (``offset + returned``); ``cache_status`` is reserved for a future read
    cache and currently reports ``"disabled"``.
    """

    execution_time_ms: float
    database_time_ms: float
    rows_scanned: int
    rows_returned: int
    cache_status: str
    generated_at: datetime

    @field_serializer("generated_at")
    def _serialize_utc(self, value: datetime) -> str:
        """Serialize datetimes as ISO-8601 UTC."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class LatestCandleResponse(BaseModel):
    """The most recent candle for a market/timeframe."""

    symbol: str
    timeframe: str
    candle: CandleDTO


class CandleStatsResponse(BaseModel):
    """Aggregate statistics for candles in a market/timeframe range."""

    symbol: str
    timeframe: str
    start: datetime | None = Field(
        None, description="Applied range start (inclusive), ISO-8601 UTC"
    )
    end: datetime | None = Field(
        None, description="Applied range end (exclusive), ISO-8601 UTC"
    )
    total_candles: int
    highest_price: Decimal | None
    lowest_price: Decimal | None
    average_volume: Decimal | None
    first_candle: CandleDTO | None = None
    last_candle: CandleDTO | None = None

    @field_serializer("highest_price", "lowest_price", "average_volume")
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        """Serialize decimals as plain strings without trailing zeros."""
        if value is None:
            return None
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text

    @field_serializer("start", "end")
    def _serialize_utc(self, value: datetime | None) -> str | None:
        """Serialize datetimes as ISO-8601 UTC (or ``null`` when unset)."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")