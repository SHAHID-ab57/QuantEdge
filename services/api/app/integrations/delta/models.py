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
