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
    version: str = Field(
        ...,
        description="Indicator-level semver, independent of the platform's own release version",
    )
    author: str
    complexity: str = Field(..., description="Free-form Big-O / performance note")
    warmup_description: str = Field(
        ...,
        description="How the warmup candle count relates to this indicator's parameters",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternate names a client's search should also match, e.g. 'MA' for 'sma'",
    )

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
            version=metadata.version,
            author=metadata.author,
            complexity=metadata.complexity,
            warmup_description=metadata.warmup_description,
            aliases=list(metadata.aliases),
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


class IndicatorBatchItemRequest(BaseModel):
    """One indicator in a batch — the request-side twin of ``IndicatorBatchItemResult``."""

    indicator: str = Field(..., description="Registered indicator name, e.g. 'sma'")
    params: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Indicator parameters as strings, same as the single-calculation "
            "endpoint's query parameters"
        ),
    )


class IndicatorBatchRequest(BaseModel):
    """A chart overlay's worth of indicators, calculated together over one shared candle range.

    Loading the candles once and running every requested indicator over
    that same in-memory list — rather than one HTTP round trip and one
    candle query per overlay — is the entire reason this endpoint exists;
    see ``IndicatorService.calculate_batch``.
    """

    timeframe: str = Field(..., examples=["1h"])
    start: datetime | None = None
    end: datetime | None = None
    limit: int | None = Field(default=None, ge=1)
    requests: list[IndicatorBatchItemRequest] = Field(..., min_length=1, max_length=50)


class IndicatorBatchItemResult(BaseModel):
    """One indicator's outcome within a batch — either a result or a domain error, never both.

    A batch never fails as a whole because one overlay was misconfigured;
    each item reports its own outcome so four correctly-configured
    indicators still render while a fifth's bad parameter is surfaced only
    against that one entry.
    """

    indicator: str
    success: bool
    label: str | None = Field(default=None, description="Present only when `success` is true")
    parameters: dict[str, Any] | None = Field(
        default=None,
        description="Fully-resolved parameters used; present only when `success` is true",
    )
    series: list[IndicatorSeriesDTO] | None = Field(
        default=None, description="Present only when `success` is true"
    )
    cache_status: str | None = Field(
        default=None, description="Present only when `success` is true"
    )
    warmup_candles: int | None = Field(
        default=None,
        description=(
            "Leading positions that are null because the indicator is not yet defined; "
            "present only when `success` is true"
        ),
    )
    execution_time_ms: float | None = Field(
        default=None,
        description=(
            "This item's own indicator calculation time; present only when `success` is true"
        ),
    )
    error_code: str | None = Field(default=None, description="Present only when `success` is false")
    error_detail: str | None = Field(
        default=None, description="Present only when `success` is false"
    )


class IndicatorBatchResponse(BaseModel):
    """The outcome of calculating every requested indicator over one shared candle range.

    ``timestamps`` is reported once, not per item: every item in
    ``results`` was calculated over the identical candle range, so their
    series all align index-for-index with this same array — duplicating it
    per item would be redundant and would risk the copies drifting apart.
    """

    symbol: str
    timeframe: str
    timestamps: list[datetime] = Field(
        ...,
        description=(
            "Candle open times shared by every result; each result's series "
            "aligns index-for-index with this"
        ),
    )
    results: list[IndicatorBatchItemResult]
    candles_analyzed: int = Field(
        ..., description="Candle count shared by every result — one candle load for the whole batch"
    )
    database_time_ms: float = Field(
        ..., description="Time spent loading candles once for the whole batch"
    )
    engine_version: str = Field(
        ..., description="The execution pipeline's own version, shared by every result"
    )
    generated_at: datetime

    @field_serializer("timestamps")
    def _serialize_timestamps(self, values: list[datetime]) -> list[str]:
        """Serialize timestamps as ISO-8601 UTC with a literal ``Z`` suffix."""
        return [value.astimezone(UTC).isoformat().replace("+00:00", "Z") for value in values]

    @field_serializer("generated_at")
    def _serialize_generated_at(self, value: datetime) -> str:
        """Serialize as ISO-8601 UTC with a literal ``Z`` suffix, matching every timestamp here."""
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
