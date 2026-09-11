"""Pydantic models for Delta Exchange API responses."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class DeltaErrorBody(BaseModel):
    """Error object returned inside a failed Delta response envelope."""

    code: int | str | None = None
    message: str | None = None


class DeltaResponse[T](BaseModel):
    """Generic envelope for Delta API responses.

    Delta wraps successful results as ``{"success": true, "result": ...}``
    and failures as ``{"success": false, "error": {...}}``.
    """

    success: bool
    result: T | None = None
    error: DeltaErrorBody | None = None


class ProductAsset(BaseModel):
    """A currency referenced by a product (underlying, quoting, settling)."""

    id: int | None = None
    symbol: str
    precision: int | None = None


class ProductSpecs(BaseModel):
    """Product specifications block returned by ``GET /v2/products``."""

    rate_exchange_interval: int | None = None


class Product(BaseModel):
    """A tradeable product returned by ``GET /v2/products``.

    Only the fields the platform consumes are modeled; extra payload fields
    are ignored by Pydantic.
    """

    id: int
    symbol: str
    contract_type: str
    state: str | None = None
    underlying_asset: ProductAsset | None = None
    quoting_asset: ProductAsset | None = None
    tick_size: str | None = None
    launch_time: datetime | None = None
    funding_method: str | None = None
    product_specs: ProductSpecs | None = None


class DeltaTickerQuotes(BaseModel):
    """Top-of-book quotes nested in a ``GET /v2/tickers`` result.

    Sizes are contract counts (strings on the wire); prices are quote-asset
    strings. All optional — an illiquid or newly listed market can have an
    empty book.
    """

    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None


class DeltaTicker(BaseModel):
    """A market ticker snapshot from ``GET /v2/tickers/{symbol}``.

    The REST counterpart of the WebSocket ``ticker`` channel, and the only
    Delta surface that carries the current ``funding_rate`` and open
    interest (``oi``) together in one call. Only the fields the platform
    consumes are modeled; Delta sends many more. Every field but ``symbol``
    is optional because coverage varies by ``contract_type`` (a spot
    market has no funding rate or open interest).

    ``timestamp`` is Unix microseconds, matching the WebSocket frames'
    ``ts``.
    """

    symbol: str
    contract_type: str | None = None
    mark_price: Decimal | None = None
    spot_price: Decimal | None = None
    close: Decimal | None = None
    funding_rate: Decimal | None = None
    #: Open interest in the underlying asset's units (Delta's ``oi``).
    oi: Decimal | None = None
    #: Open interest in contracts — matches the WebSocket ticker channel's
    #: ``oi`` field, so this is what the state-manager fill-in prefers.
    oi_contracts: Decimal | None = None
    oi_value_usd: Decimal | None = None
    turnover_usd: Decimal | None = None
    volume: Decimal | None = None
    timestamp: int | None = None
    quotes: DeltaTickerQuotes | None = None


class CandleResponse(BaseModel):
    """A single OHLCV candle returned by ``GET /v2/history/candles``.

    ``time`` is the bucket open time as a Unix timestamp in seconds.
    Decimal fields reject NaN/Inf and non-numeric payloads, so malformed
    records fail validation instead of entering the pipeline.
    """

    time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
