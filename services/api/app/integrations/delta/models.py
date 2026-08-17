"""Pydantic models for Delta Exchange API responses."""

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
