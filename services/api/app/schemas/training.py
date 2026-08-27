"""Wire schemas (DTOs) for the Machine Learning Training Framework API.

The ORM models (`app/models/training.py`) stay the source of truth for
persisted shape; this module is the one place a create request is
validated and a response is assembled — the same split
`app/schemas/experiments.py` already follows.
"""

import mimetypes
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, field_serializer

from app.models.training import TRAINING_JOB_STAGES, TRAINING_JOB_STATUSES, TRAINING_LOG_LEVELS
from app.training.base import ModelAdapterMetadata, ModelKind

if TYPE_CHECKING:
    from app.models.training import TrainingJob, TrainingJobLog

TrainingJobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
TrainingJobStage = Literal[
    "validate_dataset",
    "load_dataset",
    "initialize_model",
    "execute_training",
    "save_results",
    "update_experiment",
]
TrainingLogLevel = Literal["debug", "info", "warning", "error"]


def _iso(value: datetime) -> str:
    """ISO-8601 UTC with a literal `Z`, matching every timestamp on this API."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class TrainingJobCreateRequest(BaseModel):
    """A new training job registration, linked to an existing experiment."""

    experiment_id: uuid.UUID = Field(..., description="The experiment this job trains for")
    model_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="A registered model adapter name — see GET /training-jobs/models",
    )
    dataset_version: str | None = Field(
        default=None,
        max_length=200,
        description="Overrides the experiment's own dataset_version; defaults from it if omitted",
    )
    symbol: str | None = Field(
        default=None,
        max_length=50,
        description=(
            "Market symbol to load real candles from — required if the chosen model "
            "adapter's requires_real_data is true"
        ),
    )
    timeframe: str | None = Field(
        default=None,
        max_length=20,
        description="Candle timeframe to load, e.g. '1h' — required alongside symbol",
    )
    target_column: str | None = Field(
        default=None,
        max_length=100,
        description="Which built target column to predict; defaults to the first one built",
    )
    hyperparameters: dict[str, Any] = Field(default_factory=dict)


class TrainingJobLogDTO(BaseModel):
    id: str
    level: TrainingLogLevel
    stage: TrainingJobStage | None
    message: str
    logged_at: datetime

    @field_serializer("logged_at")
    def _serialize_logged_at(self, value: datetime) -> str:
        return _iso(value)

    @classmethod
    def from_model(cls, log: "TrainingJobLog") -> "TrainingJobLogDTO":
        return cls(
            id=str(log.id),
            level=log.level,  # type: ignore[arg-type]
            stage=log.stage,  # type: ignore[arg-type]
            message=log.message,
            logged_at=log.logged_at,
        )


class TrainingJobResponse(BaseModel):
    """A full training job record, including its logs."""

    id: str
    experiment_id: str
    dataset_version: str | None
    symbol: str | None
    timeframe: str | None
    target_column: str | None
    model_type: str
    hyperparameters: dict[str, Any]
    status: TrainingJobStatus
    current_stage: TrainingJobStage | None
    error_message: str | None
    error_detail: dict[str, Any] | None = Field(
        default=None,
        description=(
            "A structured failure report (reason, affected_feature, affected_rows, "
            "suggested_fix) recorded alongside error_message when a run fails."
        ),
    )
    result_summary: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    logs: list[TrainingJobLogDTO]
    created_at: datetime
    updated_at: datetime

    @field_serializer("started_at", "completed_at", "created_at", "updated_at")
    def _serialize_optional_timestamps(self, value: datetime | None) -> str | None:
        return None if value is None else _iso(value)

    @classmethod
    def from_model(cls, job: "TrainingJob") -> "TrainingJobResponse":
        return cls(
            id=str(job.id),
            experiment_id=str(job.experiment_id),
            dataset_version=job.dataset_version,
            symbol=job.symbol,
            timeframe=job.timeframe,
            target_column=job.target_column,
            model_type=job.model_type,
            hyperparameters=job.hyperparameters or {},
            status=job.status,  # type: ignore[arg-type]
            current_stage=job.current_stage,  # type: ignore[arg-type]
            error_message=job.error_message,
            error_detail=job.error_detail,
            result_summary=job.result_summary,
            started_at=job.started_at,
            completed_at=job.completed_at,
            logs=[TrainingJobLogDTO.from_model(log) for log in job.logs],
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class TrainingJobSummaryDTO(BaseModel):
    """One row in the training job list — metadata only, to keep a list page light."""

    id: str
    experiment_id: str
    dataset_version: str | None
    model_type: str
    status: TrainingJobStatus
    current_stage: TrainingJobStage | None
    log_count: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_timestamps(self, value: datetime) -> str:
        return _iso(value)

    @classmethod
    def from_model(cls, job: "TrainingJob") -> "TrainingJobSummaryDTO":
        return cls(
            id=str(job.id),
            experiment_id=str(job.experiment_id),
            dataset_version=job.dataset_version,
            model_type=job.model_type,
            status=job.status,  # type: ignore[arg-type]
            current_stage=job.current_stage,  # type: ignore[arg-type]
            log_count=len(job.logs),
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class TrainingJobListResponse(BaseModel):
    """One page of training jobs plus the metadata a list UI needs to paginate and filter."""

    jobs: list[TrainingJobSummaryDTO]
    total: int
    limit: int
    offset: int
    statuses: list[str] = Field(default_factory=lambda: list(TRAINING_JOB_STATUSES))
    stages: list[str] = Field(default_factory=lambda: list(TRAINING_JOB_STAGES))


class ModelAdapterDTO(BaseModel):
    """One entry in the model adapter catalogue — the frontend's model-type dropdown source."""

    name: str
    label: str
    description: str
    framework: str
    model_kind: ModelKind = Field(
        description=(
            "'classification' or 'regression' for a real baseline adapter, "
            "'placeholder' for the fabricated one — tells the frontend whether to "
            "render a confusion matrix or regression metrics."
        )
    )
    requires_real_data: bool = Field(
        description="Whether a job using this adapter requires symbol/timeframe/target_column"
    )
    hyperparameter_hints: list[str]
    version: str

    @classmethod
    def from_metadata(cls, metadata: ModelAdapterMetadata) -> "ModelAdapterDTO":
        return cls(
            name=metadata.name,
            label=metadata.label,
            description=metadata.description,
            framework=metadata.framework,
            model_kind=metadata.model_kind,
            requires_real_data=metadata.requires_real_data,
            hyperparameter_hints=list(metadata.hyperparameter_hints),
            version=metadata.version,
        )


class ModelAdapterCatalogResponse(BaseModel):
    """Every registered model adapter, for a frontend dropdown/catalogue view."""

    adapters: list[ModelAdapterDTO]


class TrainingJobPredictRequest(BaseModel):
    """One or more feature rows to predict for, using a completed job's trained model."""

    rows: list[list[float]] = Field(
        ...,
        min_length=1,
        description="Each row must have exactly as many values as the job's feature_columns",
    )


class TrainingJobPredictResponse(BaseModel):
    """Predictions for each requested row, in the same order.

    `probabilities`/`confidence_levels`/`classes` are populated only when the job's
    model adapter supports `predict_proba` (today: `logistic_regression`) — `None`
    for every other adapter, never a fabricated confidence.
    """

    predictions: list[Any]
    feature_columns: list[str] | None = Field(
        default=None,
        description="The feature columns (in order) this job's model expects, if recorded",
    )
    classes: list[Any] | None = Field(
        default=None,
        description="The model's class labels, in the same order as each row of probabilities",
    )
    probabilities: list[list[float]] | None = Field(
        default=None,
        description="Per-row, per-class probability, aligned with classes — only for a classifier",
    )
    confidence_levels: list[str] | None = Field(
        default=None,
        description="Per-row 'high'/'medium'/'low', from the predicted class's own probability",
    )


class TrainingArtifactDTO(BaseModel):
    """One downloadable file produced by a completed job's training run."""

    artifact_type: str = Field(description="e.g. 'model_joblib', 'metrics_json', 'roc_curve_png'")
    filename: str
    content_type: str
    download_url: str

    @classmethod
    def build(cls, job_id: uuid.UUID, artifact_type: str, uri: str) -> "TrainingArtifactDTO":
        filename = Path(uri.removeprefix("file://")).name
        content_type, _ = mimetypes.guess_type(filename)
        return cls(
            artifact_type=artifact_type,
            filename=filename,
            content_type=content_type or "application/octet-stream",
            download_url=f"/api/v1/training-jobs/{job_id}/artifacts/{artifact_type}",
        )


class TrainingArtifactListResponse(BaseModel):
    """Every downloadable artifact a completed job's training run produced."""

    job_id: str
    artifacts: list[TrainingArtifactDTO]


__all__ = [
    "TRAINING_LOG_LEVELS",
    "ModelAdapterCatalogResponse",
    "ModelAdapterDTO",
    "TrainingArtifactDTO",
    "TrainingArtifactListResponse",
    "TrainingJobCreateRequest",
    "TrainingJobListResponse",
    "TrainingJobLogDTO",
    "TrainingJobPredictRequest",
    "TrainingJobPredictResponse",
    "TrainingJobResponse",
    "TrainingJobSummaryDTO",
]
