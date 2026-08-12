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
