"""Response schemas (DTOs) for the feature engineering API.

The engine's own dataclasses (``FeatureMetadata``, ``FeatureDataset``, …)
are deliberately Pydantic-free so generators stay independent of the web
layer; this module is the one place those are mapped to the wire — the same
split ``app/schemas/indicators.py`` makes.

Feature values serialize as JSON numbers, booleans, or strings according to
each column's declared ``dtype``, never as the decimal-as-string convention
the candle DTOs use: a feature is a model input, and a model consumes
floats.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_serializer

from app.features.base import FeatureColumn, FeatureMetadata
from app.features.correlation import FeatureCorrelationMatrix
from app.features.dataset import DatasetFeatureInfo, FeatureDataset
from app.features.lineage import FeatureLineageGraph, FeatureLineageNode
from app.features.quality import DatasetQualityReport, FeatureFailure
from app.features.statistics import ColumnStatistics, DatasetStatistics
from app.schemas.indicators import ParameterSpecDTO


class FeatureDTO(BaseModel):
    """One feature generator's full catalogue entry.

    Intentionally the same shape as ``IndicatorDTO`` — a client that can
    already render the indicator catalogue can render this one with no new
    component.
    """

    name: str
    label: str
    description: str
    category: str
    parameters: list[ParameterSpecDTO]
    outputs: list[str] = Field(
        default_factory=list,
        description="Column-name templates this generator produces, e.g. 'sma_{period}'",
    )
    version: str = Field(
        ...,
        description="Generator-level semver; a change means previously-built datasets differ",
    )
    author: str
    complexity: str = Field(..., description="Free-form Big-O / performance note")
    warmup_description: str = Field(
        ..., description="How the warmup relates to this generator's parameters"
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternate names a client's search should also match",
    )
    unit: str = Field(
        default="", description="Free-form unit of the produced values, e.g. 'price' or 'ratio'"
    )
    value_type: str = Field(
        default="float",
        description="Predominant column dtype: 'float', 'int', 'bool', 'categorical', or 'mixed'",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Other registered features this one depends on (see the AI extension points)",
    )
    is_deterministic: bool = Field(
        default=True,
        description="Whether identical candles and parameters always produce identical output",
    )
    missing_values_expected: bool = Field(
        default=False,
        description="Whether this generator can produce nulls beyond its declared warmup",
    )

    @classmethod
    def from_metadata(cls, metadata: FeatureMetadata) -> "FeatureDTO":
        """Map engine metadata onto the wire DTO."""
        return cls(
            name=metadata.name,
            label=metadata.label,
            description=metadata.description,
            category=metadata.category,
            parameters=[ParameterSpecDTO.from_spec(spec) for spec in metadata.parameters],
            outputs=list(metadata.outputs),
            version=metadata.version,
            author=metadata.author,
            complexity=metadata.complexity,
            warmup_description=metadata.warmup_description,
            aliases=list(metadata.aliases),
            unit=metadata.unit,
            value_type=metadata.value_type,
            dependencies=list(metadata.dependencies),
            is_deterministic=metadata.is_deterministic,
            missing_values_expected=metadata.missing_values_expected,
        )


class FeatureCatalogResponse(BaseModel):
    """Every feature generator the pipeline can run."""

    features: list[FeatureDTO]
    total: int = Field(..., description="Number of registered generators")
    categories: list[str] = Field(
        ..., description="Distinct categories present, for grouping in a UI"
    )


class FeatureColumnDTO(BaseModel):
    """One column in a built dataset."""

    name: str
    label: str
    description: str = ""
    dtype: str = Field(..., description='"float", "int", "bool", or "categorical"')

    @classmethod
    def from_column(cls, column: FeatureColumn) -> "FeatureColumnDTO":
        """Map an engine ``FeatureColumn`` onto the wire DTO."""
        return cls(
            name=column.name,
            label=column.label,
            description=column.description,
            dtype=column.dtype,
        )


class DatasetFeatureInfoDTO(BaseModel):
    """How one requested feature resolved, for the dataset's provenance record."""

    feature: str
    label: str
    version: str
    parameters: dict[str, Any] = Field(
        ..., description="Fully-resolved parameters used, including applied defaults"
    )
    columns: list[str]
    warmup: int
    execution_time_ms: float
    cache_status: str = Field(
        default="disabled",
        description='"hit", "miss", or "disabled" — see the Feature Cache',
    )

    @classmethod
    def from_info(cls, info: DatasetFeatureInfo) -> "DatasetFeatureInfoDTO":
        """Map an engine ``DatasetFeatureInfo`` onto the wire DTO."""
        return cls(
            feature=info.feature,
            label=info.label,
            version=info.version,
            parameters=info.params,
            columns=info.columns,
            warmup=info.warmup,
            execution_time_ms=info.execution_time_ms,
            cache_status=info.cache_status,
        )


class FeatureFailureDTO(BaseModel):
    """One requested feature that could not be generated, and why."""

    feature: str
    params: dict[str, Any]
    error_code: str
    error_detail: str

    @classmethod
    def from_failure(cls, failure: FeatureFailure) -> "FeatureFailureDTO":
        """Map an engine ``FeatureFailure`` onto the wire DTO."""
        return cls(
            feature=failure.feature,
            params=failure.params,
            error_code=failure.error_code,
            error_detail=failure.error_detail,
        )


class DatasetQualityReportDTO(BaseModel):
    """How trustworthy a built dataset is, and what was done about it."""

    total_rows: int = Field(..., description="Candles loaded before warmup trimming")
    rows_returned: int = Field(..., description="Rows in the response actually sent back")
    rows_removed: int = Field(
        ..., description="Rows dropped because at least one feature was still undefined"
    )
    null_counts: dict[str, int] = Field(
        default_factory=dict, description="Null count per column, before warmup trimming"
    )
    duplicate_timestamps: int = Field(
        default=0, description="Candle timestamps appearing more than once (expected: 0)"
    )
    missing_candles: int = Field(
        default=0, description="Gaps in the loaded candle range at this timeframe's cadence"
    )
    feature_failures: list[FeatureFailureDTO] = Field(
        default_factory=list, description="Requested features that failed to generate"
    )
    generation_time_ms: float = Field(
        default=0.0, description="Wall-clock time spent running every requested generator"
    )

    @classmethod
    def from_report(cls, report: DatasetQualityReport) -> "DatasetQualityReportDTO":
        """Map an engine ``DatasetQualityReport`` onto the wire DTO."""
        return cls(
            total_rows=report.total_rows,
            rows_returned=report.rows_returned,
            rows_removed=report.rows_removed,
            null_counts=report.null_counts,
            duplicate_timestamps=report.duplicate_timestamps,
            missing_candles=report.missing_candles,
            feature_failures=[
                FeatureFailureDTO.from_failure(failure) for failure in report.feature_failures
            ],
            generation_time_ms=report.generation_time_ms,
        )


class FeatureDatasetMeta(BaseModel):
    """How the dataset was produced — volume, trimming, timing, and versions."""

    row_count: int = Field(..., description="Rows in the returned dataset")
    total_rows: int = Field(
        ...,
        description="Rows in the full dataset before any preview truncation",
    )
    candles_analyzed: int = Field(..., description="Candles loaded before warmup trimming")
    rows_dropped: int = Field(
        ..., description="Rows removed because at least one feature was still in warmup"
    )
    warmup_candles: int = Field(..., description="Largest warmup across every requested feature")
    truncated: bool = Field(
        ...,
        description=(
            "True when the response was capped by `preview_rows`; export to get everything"
        ),
    )
    database_time_ms: float
    pipeline_version: str
    generated_at: datetime

    @field_serializer("generated_at")
    def _serialize_generated_at(self, value: datetime) -> str:
        """ISO-8601 UTC with a literal ``Z``, matching every timestamp on this API."""
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class FeatureDatasetResponse(BaseModel):
    """A built feature dataset: the matrix, its columns, and its provenance.

    Row-oriented (``rows`` parallel to ``timestamps``) because that is the
    shape a preview table and a CSV writer both want, and because it keeps
    a wide dataset compact on the wire — repeating every column name per
    row, as a records-oriented shape would, roughly doubles the payload.
    """

    dataset_id: str = Field(
        ..., description="Unique per build; identifies this exact dataset snapshot"
    )
    symbol: str
    timeframe: str
    columns: list[FeatureColumnDTO]
    timestamps: list[datetime] = Field(
        ..., description="Candle open times; each row aligns index-for-index with this"
    )
    rows: list[list[Any]] = Field(
        ..., description="One row per timestamp, values ordered as `columns`"
    )
    features: list[DatasetFeatureInfoDTO]
    meta: FeatureDatasetMeta
    quality: DatasetQualityReportDTO

    @field_serializer("timestamps")
    def _serialize_timestamps(self, values: list[datetime]) -> list[str]:
        """Serialize timestamps as ISO-8601 UTC with a literal ``Z`` suffix."""
        return [value.astimezone(UTC).isoformat().replace("+00:00", "Z") for value in values]

    @classmethod
    def from_dataset(
        cls,
        dataset: FeatureDataset,
        *,
        database_time_ms: float,
        preview_rows: int | None = None,
    ) -> "FeatureDatasetResponse":
        """Map a built dataset onto the wire, optionally truncating for preview.

        Truncation is reported rather than silent: ``meta.truncated`` and
        ``meta.total_rows`` always describe the *full* dataset, so a client
        can tell a 200-row preview of a 50,000-row dataset from a genuinely
        200-row one. Getting that wrong would let someone export what they
        saw and unknowingly train on a fraction of their data.
        """
        total = dataset.row_count
        limit = total if preview_rows is None else min(preview_rows, total)
        return cls(
            dataset_id=dataset.dataset_id,
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            columns=[FeatureColumnDTO.from_column(column) for column in dataset.columns],
            timestamps=dataset.timestamps[:limit],
            rows=dataset.rows[:limit],
            features=[DatasetFeatureInfoDTO.from_info(info) for info in dataset.features],
            quality=DatasetQualityReportDTO.from_report(dataset.quality),
            meta=FeatureDatasetMeta(
                row_count=limit,
                total_rows=total,
                candles_analyzed=dataset.candles_analyzed,
                rows_dropped=dataset.rows_dropped,
                warmup_candles=dataset.warmup_candles,
                truncated=limit < total,
                database_time_ms=database_time_ms,
                pipeline_version=dataset.pipeline_version,
                generated_at=dataset.generated_at,
            ),
        )


class FeatureRequestItem(BaseModel):
    """One feature to include in a dataset."""

    feature: str = Field(..., description="Registered feature name, e.g. 'sma'", examples=["sma"])
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Feature parameters; validated against the generator's own specs",
    )


class FeatureDatasetRequest(BaseModel):
    """A dataset build request: one market/timeframe/range, several features."""

    timeframe: str = Field(..., examples=["1h"])
    start: datetime | None = None
    end: datetime | None = None
    limit: int | None = Field(
        default=None,
        ge=1,
        description="Maximum candles to load; defaults to the server page size",
    )
    features: list[FeatureRequestItem] = Field(..., min_length=1, max_length=50)
    drop_warmup: bool = Field(
        default=True,
        description=(
            "Drop rows where any requested feature is still undefined. True by "
            "default because a training matrix must not contain nulls; the count "
            "removed is always reported in `meta.rows_dropped`."
        ),
    )
    preview_rows: int | None = Field(
        default=None,
        ge=1,
        le=5000,
        description="Cap rows in the response for preview; `meta` still describes the full dataset",
    )


class FeatureCorrelationResponse(BaseModel):
    """Pairwise Pearson correlation across every numeric column in a built dataset."""

    symbol: str
    timeframe: str
    columns: list[str] = Field(
        default_factory=list, description="Numeric columns compared, in matrix row/column order"
    )
    matrix: list[list[float]] = Field(
        default_factory=list,
        description="matrix[i][j] is the correlation between columns[i] and columns[j]",
    )
    row_count: int = Field(
        default=0, description="Rows actually used (pairwise-complete per column pair)"
    )

    @classmethod
    def from_matrix(
        cls, symbol: str, timeframe: str, matrix: FeatureCorrelationMatrix
    ) -> "FeatureCorrelationResponse":
        """Map an engine ``FeatureCorrelationMatrix`` onto the wire DTO."""
        return cls(
            symbol=symbol,
            timeframe=timeframe,
            columns=matrix.columns,
            matrix=matrix.matrix,
            row_count=matrix.row_count,
        )


class ColumnStatisticsDTO(BaseModel):
    """Summary statistics for one column over a full (non-preview-capped) dataset."""

    column: str
    count: int
    null_count: int
    mean: float | None = None
    std: float | None = None
    minimum: float | None = None
    maximum: float | None = None

    @classmethod
    def from_statistics(cls, stats: ColumnStatistics) -> "ColumnStatisticsDTO":
        """Map an engine ``ColumnStatistics`` onto the wire DTO."""
        return cls(
            column=stats.column,
            count=stats.count,
            null_count=stats.null_count,
            mean=stats.mean,
            std=stats.std,
            minimum=stats.minimum,
            maximum=stats.maximum,
        )


class FeatureStatisticsResponse(BaseModel):
    """Per-column statistics for every column in a built dataset."""

    symbol: str
    timeframe: str
    columns: list[ColumnStatisticsDTO] = Field(default_factory=list)
    row_count: int = 0

    @classmethod
    def from_statistics(
        cls, symbol: str, timeframe: str, statistics: DatasetStatistics
    ) -> "FeatureStatisticsResponse":
        """Map an engine ``DatasetStatistics`` onto the wire DTO."""
        return cls(
            symbol=symbol,
            timeframe=timeframe,
            columns=[ColumnStatisticsDTO.from_statistics(entry) for entry in statistics.columns],
            row_count=statistics.row_count,
        )


class FeatureLineageNodeDTO(BaseModel):
    """One feature's place in the dependency graph."""

    name: str
    label: str
    category: str
    dependencies: list[str] = Field(
        default_factory=list, description="Features this one directly depends on"
    )
    depended_on_by: list[str] = Field(
        default_factory=list, description="Features that directly depend on this one"
    )
    ancestors: list[str] = Field(
        default_factory=list, description="Every feature this one transitively depends on"
    )
    descendants: list[str] = Field(
        default_factory=list, description="Every feature that transitively depends on this one"
    )

    @classmethod
    def from_node(cls, node: FeatureLineageNode) -> "FeatureLineageNodeDTO":
        """Map an engine ``FeatureLineageNode`` onto the wire DTO."""
        return cls(
            name=node.name,
            label=node.label,
            category=node.category,
            dependencies=list(node.dependencies),
            depended_on_by=list(node.depended_on_by),
            ancestors=list(node.ancestors),
            descendants=list(node.descendants),
        )


class FeatureLineageResponse(BaseModel):
    """The whole registry's dependency structure, resolved.

    Every registered feature's own metadata declares no dependency today
    (see ``FeatureMetadata.dependencies``'s own docstring) — a real
    response from this endpoint therefore has zero ``edges`` until a future
    generator declares one, which is the honest, current state rather than
    a placeholder: the graph, cycle detection, and topological order are
    all real and already exercised by the registry's own startup
    validation, simply over an edgeless graph today.
    """

    nodes: list[FeatureLineageNodeDTO] = Field(default_factory=list)
    edges: list[tuple[str, str]] = Field(
        default_factory=list, description="(dependency, dependent) pairs"
    )
    topological_order: list[str] = Field(default_factory=list)

    @classmethod
    def from_graph(cls, graph: FeatureLineageGraph) -> "FeatureLineageResponse":
        """Map an engine ``FeatureLineageGraph`` onto the wire DTO."""
        return cls(
            nodes=[FeatureLineageNodeDTO.from_node(node) for node in graph.nodes],
            edges=graph.edges,
            topological_order=graph.topological_order,
        )
