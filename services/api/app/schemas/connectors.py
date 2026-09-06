"""Response schemas (DTOs) for the External Data Connectors API.

Backs the Data Sources page (`ARCHITECTURE.md` § "External Data
Connectors" → "Data Sources Page"): a registry-driven catalogue
(`GET /connectors`), intentionally the same "catalogue reads straight from
the registry, no source hardcoded" shape `FeatureDTO`/`app.schemas.features`
already established for `/features`; and a paginated time series
(`GET /connectors/{source}/history`) mirroring `CandleDTO`/`Pagination`'s
own limit/offset shape in `app.schemas.market_data`, kept as a separate,
smaller pair of models rather than importing those — a connector's own
value is a bare float, never OHLCV, and this table's own inclusive-range
convention differs from `Candle.open_time`'s half-open one (see
`app.repositories.external_data.ExternalDataRepository.list_between`'s own
docstring).
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


def _ensure_utc(value: datetime) -> datetime:
    """Normalize a timestamp to aware UTC for a stable JSON contract.

    Without this, a naive datetime (SQLite's own round-trip quirk for
    `DateTime(timezone=True)` columns — see `ExternalDataRepository`'s own
    `_as_utc` docstring) would serialize with no timezone suffix at all,
    silently failing the frontend's strict `z.string().datetime()` check —
    the same normalization `CandleDTO._ensure_utc` already applies for
    candles.
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ConnectorDTO(BaseModel):
    """One registered connector's catalogue entry, plus its most recent
    stored value — everything the "Active Data Sources" page needs for
    one card, in one response, so it never has to make a second request
    per connector just to know what to show before a chart loads."""

    source: str
    label: str
    description: str
    frequency: str = Field(
        default="", description="Free-form update cadence this source publishes at, e.g. 'daily'"
    )
    requires_auth: bool = False
    latest_value: float | None = Field(
        default=None,
        description="Most recently published value, or null if nothing has been ingested yet",
    )
    latest_timestamp: datetime | None = Field(
        default=None, description="That value's own timestamp, or null if nothing is stored yet"
    )

    @field_validator("latest_timestamp", mode="before")
    @classmethod
    def _validate_latest_timestamp(cls, value: datetime | None) -> datetime | None:
        return _ensure_utc(value) if value is not None else None


class ConnectorCatalogResponse(BaseModel):
    """Every registered connector — reads straight from `ConnectorRegistry`,
    so a future connector (Marketaux, Etherscan, FRED, DefiLlama, CoinGecko)
    appears here with no change to this schema or the endpoint that builds
    it, the same guarantee `FeatureCatalogResponse` already gives `/features`.
    """

    connectors: list[ConnectorDTO]
    total: int = Field(..., description="Number of registered connectors")


class ExternalDataPointDTO(BaseModel):
    """One stored point, for charting — just enough to plot a trend line."""

    timestamp: datetime
    value: float

    @field_validator("timestamp", mode="before")
    @classmethod
    def _validate_timestamp(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class ConnectorHistoryPagination(BaseModel):
    """Pagination metadata for a connector history page — the same
    total/returned/has_more/limit/offset shape `Pagination` (candles) uses,
    declared separately rather than imported: this endpoint's own
    `limit`/`offset` defaults are unrelated to candles' own."""

    total: int = Field(..., description="Total points matching the query")
    returned: int = Field(..., description="Points returned in this page")
    has_more: bool = Field(..., description="Whether further pages exist")
    limit: int
    offset: int


class ConnectorHistoryResponse(BaseModel):
    """A page of one connector's stored history, oldest first."""

    source: str
    items: list[ExternalDataPointDTO]
    pagination: ConnectorHistoryPagination
