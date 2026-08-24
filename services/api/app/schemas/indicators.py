"""Response schemas (DTOs) for the indicator API.

The engine's own dataclasses (``IndicatorMetadata``, ``IndicatorSeries``,
…) are deliberately Pydantic-free so indicators stay independent of the web
layer; this module is the one place those are mapped to the wire.

Indicator values serialize as JSON numbers rather than the decimal-as-string
convention the candle DTOs use. That is intentional: an EMA or RSI is a
float approximation by construction, and rendering it as a lossless decimal
string would imply a precision the calculation does not have.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.indicators.base import IndicatorMetadata, IndicatorSeries, SeriesSpec
from app.indicators.params import ParameterSpec


class ParameterSpecDTO(BaseModel):
    """One parameter an indicator accepts, as advertised to clients.

    A UI can build a complete, correctly-constrained input form from this
    alone — which is the point of publishing it rather than hardcoding each
    indicator's form on the frontend.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str
    type: str
    label: str
    description: str
    default: Any = None
    required: bool
    minimum: float | None = None
    maximum: float | None = None
    choices: list[str] = Field(default_factory=list)

    @classmethod
    def from_spec(cls, spec: ParameterSpec) -> "ParameterSpecDTO":
        """Map an engine ``ParameterSpec`` onto the wire DTO."""
        return cls(
            name=spec.name,
            type=spec.type,
            label=spec.label,
            description=spec.description,
            default=spec.default,
            required=spec.required,
            minimum=spec.minimum,
            maximum=spec.maximum,
            choices=list(spec.choices),
        )


class SeriesSpecDTO(BaseModel):
    """One output series an indicator will produce."""

    name: str
    label: str
    description: str = ""

    @classmethod
    def from_spec(cls, spec: SeriesSpec) -> "SeriesSpecDTO":
        """Map an engine ``SeriesSpec`` onto the wire DTO."""
        return cls(name=spec.name, label=spec.label, description=spec.description)


class IndicatorDTO(BaseModel):
    """An indicator's full catalogue entry."""

    name: str
    label: str
    description: str
    category: str
    parameters: list[ParameterSpecDTO]
    outputs: list[SeriesSpecDTO]

    @classmethod
    def from_metadata(cls, metadata: IndicatorMetadata) -> "IndicatorDTO":
        """Map engine metadata onto the wire DTO."""
        return cls(
            name=metadata.name,
            label=metadata.label,
            description=metadata.description,
            category=metadata.category,
            parameters=[ParameterSpecDTO.from_spec(spec) for spec in metadata.parameters],
            outputs=[SeriesSpecDTO.from_spec(spec) for spec in metadata.outputs],
        )


class IndicatorCatalogResponse(BaseModel):
    """Every indicator the engine can run."""

    indicators: list[IndicatorDTO]
    total: int = Field(..., description="Number of registered indicators")
    categories: list[str] = Field(
        ...,
        description="Distinct categories present, for grouping in a UI",
    )


class IndicatorSeriesDTO(BaseModel):
    """One computed series, aligned index-for-index with ``timestamps``.

    ``null`` marks a warmup position where the indicator is not yet
    defined — never a calculation failure, which surfaces as an error
    response instead.
    """

    name: str
    label: str
    values: list[float | None]

    @classmethod
    def from_series(cls, series: IndicatorSeries) -> "IndicatorSeriesDTO":
        """Map an engine ``IndicatorSeries`` onto the wire DTO."""
        return cls(name=series.name, label=series.label, values=series.values)


class IndicatorCalculationMeta(BaseModel):
    """How the result was produced — timing, cache status, and data volume."""

    candles_analyzed: int
    warmup_candles: int = Field(
        ...,
        description="Leading positions that are null because the indicator is not yet defined",
    )
    execution_time_ms: float = Field(..., description="Indicator calculation time")
    database_time_ms: float = Field(..., description="Time spent loading candles")
    cache_status: str = Field(..., description='"hit", "miss", or "disabled"')
    generated_at: datetime

    @field_serializer("generated_at")
    def _serialize_datetime(self, value: datetime) -> str:
        """Serialize as ISO-8601 UTC with a literal ``Z`` suffix.

        Matches the convention the rest of this API uses; the frontend's
        Zod schemas validate with ``z.string().datetime()``, which rejects a
        ``+00:00`` offset.
        """
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class IndicatorCalculationResponse(BaseModel):
    """One indicator computed over one market/timeframe range."""

    symbol: str
    timeframe: str
    indicator: IndicatorDTO
    parameters: dict[str, Any] = Field(
        ...,
        description="The fully-resolved parameters used, including applied defaults",
    )
    timestamps: list[datetime] = Field(
        ...,
        description="Candle open times; every series aligns index-for-index with this",
    )
    series: list[IndicatorSeriesDTO]
    meta: IndicatorCalculationMeta

    @field_serializer("timestamps")
    def _serialize_timestamps(self, values: list[datetime]) -> list[str]:
        """Serialize timestamps as ISO-8601 UTC with a literal ``Z`` suffix."""
        return [value.astimezone(UTC).isoformat().replace("+00:00", "Z") for value in values]
