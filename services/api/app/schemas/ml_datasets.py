"""Response schemas (DTOs) for the ML Dataset Builder API.

The engine's own dataclasses (`MLDataset`, `TargetMetadata`, …) stay
Pydantic-free; this module is the one place those are mapped to the wire —
the same split every other engine on this platform follows. Reuses
`FeatureColumnDTO`, `DatasetFeatureInfoDTO`, `DatasetQualityReportDTO`, and
`FeatureDatasetRequest` from `app.schemas.features` (a target-appended
matrix is still a `FeatureDataset` under the hood — see
`app/ml_datasets/dataset.py`) and the entire `ValidationReportResponse`
from `app.schemas.dataset_validation`, rather than redeclaring any of them.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_serializer

from app.ml_datasets.base import TargetMetadata
from app.ml_datasets.dataset import DatasetTargetInfo, MLDataset
from app.schemas.dataset_validation import ValidationReportResponse
from app.schemas.features import (
    DatasetFeatureInfoDTO,
    DatasetQualityReportDTO,
    FeatureColumnDTO,
    FeatureDatasetRequest,
)
from app.schemas.indicators import ParameterSpecDTO


class TargetDTO(BaseModel):
    """One target generator's full catalogue entry — the target-side counterpart to `FeatureDTO`."""

    name: str
    label: str
    description: str
    category: str
    parameters: list[ParameterSpecDTO]
    outputs: list[str] = Field(
        default_factory=list,
        description="Column-name templates this target produces, e.g. 'next_close_{horizon}'",
    )
    version: str
    author: str
    value_type: str = Field(
        default="float", description="'float' or 'categorical' — the target's predominant dtype"
    )
    default_horizon: int = Field(
        ..., description="Candles ahead this target looks when `horizon` isn't overridden"
    )
    is_deterministic: bool = True

    @classmethod
    def from_metadata(cls, metadata: TargetMetadata) -> "TargetDTO":
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
            value_type=metadata.value_type,
            default_horizon=metadata.default_horizon,
            is_deterministic=metadata.is_deterministic,
        )


class TargetCatalogResponse(BaseModel):
    """Every prediction-target generator the pipeline can run."""

    targets: list[TargetDTO]
    total: int = Field(..., description="Number of registered target generators")
    categories: list[str] = Field(
        ..., description="Distinct categories present, for grouping in a UI"
    )


class MLTargetRequestItem(BaseModel):
    """One prediction target to include in an ML dataset."""

    target: str = Field(
        ..., description="Registered target name, e.g. 'next_close'", examples=["next_close"]
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Target parameters (e.g. horizon); validated against the generator's own specs",
    )


class MLDatasetRequest(FeatureDatasetRequest):
    """A dataset-build request plus targets and a train/validation/test split.

    Subclasses `FeatureDatasetRequest` rather than duplicating its fields —
    the same composition `DatasetValidationRequest` already uses — so the
    exact same market/timeframe/range/feature-selection request that builds
    a plain feature dataset also builds a fully versioned, split, validated
    ML dataset; a caller changes only the URL and adds `targets`.
    """

    targets: list[MLTargetRequestItem] = Field(..., min_length=1, max_length=20)
    drop_undefined_targets: bool = Field(
        default=True,
        description=(
            "Drop trailing rows where any requested target is still undefined (no future "
            "candle exists yet to compute it from). True by default because a training "
            "matrix must not contain missing labels."
        ),
    )
    split_train: float = Field(default=0.7, ge=0.0, le=1.0)
    split_validation: float = Field(default=0.15, ge=0.0, le=1.0)
    split_test: float = Field(default=0.15, ge=0.0, le=1.0)


class TargetFailureDTO(BaseModel):
    """One requested target that could not be generated, and why."""

    target: str
    params: dict[str, Any]
    error_code: str
    error_detail: str


class DatasetTargetInfoDTO(BaseModel):
    """How one requested target resolved, for the dataset's provenance record."""

    target: str
    label: str
    version: str
    parameters: dict[str, Any] = Field(
        ..., description="Fully-resolved parameters used, including applied defaults"
    )
    columns: list[str]
    horizon: int
    execution_time_ms: float

    @classmethod
    def from_info(cls, info: DatasetTargetInfo) -> "DatasetTargetInfoDTO":
        """Map an engine `DatasetTargetInfo` onto the wire DTO."""
        return cls(
            target=info.target,
            label=info.label,
            version=info.version,
            parameters=info.params,
            columns=info.columns,
            horizon=info.horizon,
            execution_time_ms=info.execution_time_ms,
        )


class SplitRatiosDTO(BaseModel):
    """Fractions of a dataset's rows assigned to each split."""

    train: float
    validation: float
    test: float


class SplitBoundsDTO(BaseModel):
    """Row counts actually assigned to each split, after chronological slicing."""

    train_rows: int
    validation_rows: int
    test_rows: int


class MLDatasetMeta(BaseModel):
    """How the ML dataset was produced — volume, trimming, timing, and versions."""

    row_count: int = Field(..., description="Rows in the returned (pre-split) dataset")
    total_rows: int = Field(
        ..., description="Rows in the full dataset before any preview truncation"
    )
    candles_analyzed: int
    rows_dropped_warmup: int = Field(
        ..., description="Rows removed because at least one feature was still in warmup"
    )
    rows_dropped_horizon: int = Field(
        ..., description="Rows removed because at least one target was still undefined"
    )
    warmup_candles: int
    max_horizon: int = Field(..., description="Largest horizon across every requested target")
    truncated: bool = Field(..., description="True when the response was capped by `preview_rows`")
    database_time_ms: float
    pipeline_version: str
    target_pipeline_version: str
    builder_version: str
    generated_at: datetime
    created_at: datetime

    @field_serializer("generated_at", "created_at")
    def _serialize_timestamps(self, value: datetime) -> str:
        """ISO-8601 UTC with a literal ``Z``, matching every timestamp on this API."""
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class MLDatasetResponse(BaseModel):
    """A built, validated, split ML dataset — the matrix, its provenance, and its verdict."""

    ml_dataset_id: str = Field(
        ..., description="Unique per build; identifies this exact ML artifact"
    )
    dataset_id: str = Field(..., description="The underlying feature build's own identity")
    symbol: str
    timeframe: str
    columns: list[FeatureColumnDTO]
    feature_columns: list[str] = Field(..., description="Which columns are model inputs (X)")
    target_columns: list[str] = Field(..., description="Which columns are prediction labels (y)")
    timestamps: list[datetime] = Field(
        ..., description="Candle open times; each row aligns index-for-index with this"
    )
    rows: list[list[Any]] = Field(
        ..., description="One row per timestamp, values ordered as `columns`"
    )
    split: list[str] = Field(
        ..., description="Per-row split label ('train'/'validation'/'test'), parallel to `rows`"
    )
    features: list[DatasetFeatureInfoDTO]
    targets: list[DatasetTargetInfoDTO]
    target_failures: list[TargetFailureDTO] = Field(
        default_factory=list, description="Requested targets that failed to generate"
    )
    split_ratios: SplitRatiosDTO
    split_bounds: SplitBoundsDTO
    quality: DatasetQualityReportDTO
    validation: ValidationReportResponse
    meta: MLDatasetMeta

    @field_serializer("timestamps")
    def _serialize_timestamps(self, values: list[datetime]) -> list[str]:
        """Serialize timestamps as ISO-8601 UTC with a literal ``Z`` suffix."""
        return [value.astimezone(UTC).isoformat().replace("+00:00", "Z") for value in values]

    @classmethod
    def from_ml_dataset(
        cls,
        ml_dataset: MLDataset,
        *,
        database_time_ms: float,
        preview_rows: int | None = None,
    ) -> "MLDatasetResponse":
        """Map a built `MLDataset` onto the wire, optionally truncating for preview.

        Truncation is reported, never silent — matching
        `FeatureDatasetResponse.from_dataset`'s exact contract, since a
        truncated ML dataset preview must never be mistaken for the whole
        training set.
        """
        dataset = ml_dataset.dataset
        total = dataset.row_count
        limit = total if preview_rows is None else min(preview_rows, total)
        split_labels = (
            ["train"] * ml_dataset.split.train.row_count
            + ["validation"] * ml_dataset.split.validation.row_count
            + ["test"] * ml_dataset.split.test.row_count
        )

        return cls(
            ml_dataset_id=ml_dataset.ml_dataset_id,
            dataset_id=dataset.dataset_id,
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            columns=[FeatureColumnDTO.from_column(column) for column in dataset.columns],
            feature_columns=list(ml_dataset.feature_columns),
            target_columns=list(ml_dataset.target_columns),
            timestamps=dataset.timestamps[:limit],
            rows=dataset.rows[:limit],
            split=split_labels[:limit],
            features=[DatasetFeatureInfoDTO.from_info(info) for info in dataset.features],
            targets=[DatasetTargetInfoDTO.from_info(info) for info in ml_dataset.targets],
            target_failures=[
                TargetFailureDTO(
                    target=failure.feature,
                    params=failure.params,
                    error_code=failure.error_code,
                    error_detail=failure.error_detail,
                )
                for failure in ml_dataset.target_failures
            ],
            split_ratios=SplitRatiosDTO(
                train=ml_dataset.split_ratios.train,
                validation=ml_dataset.split_ratios.validation,
                test=ml_dataset.split_ratios.test,
            ),
            split_bounds=SplitBoundsDTO(
                train_rows=ml_dataset.split.train.row_count,
                validation_rows=ml_dataset.split.validation.row_count,
                test_rows=ml_dataset.split.test.row_count,
            ),
            quality=DatasetQualityReportDTO.from_report(dataset.quality),
            validation=ValidationReportResponse.from_report(ml_dataset.validation),
            meta=MLDatasetMeta(
                row_count=limit,
                total_rows=total,
                candles_analyzed=dataset.candles_analyzed,
                rows_dropped_warmup=dataset.rows_dropped,
                rows_dropped_horizon=ml_dataset.rows_dropped_for_horizon,
                warmup_candles=dataset.warmup_candles,
                max_horizon=ml_dataset.max_horizon,
                truncated=limit < total,
                database_time_ms=database_time_ms,
                pipeline_version=dataset.pipeline_version,
                target_pipeline_version=ml_dataset.target_pipeline_version,
                builder_version=ml_dataset.builder_version,
                generated_at=dataset.generated_at,
                created_at=ml_dataset.created_at,
            ),
        )
