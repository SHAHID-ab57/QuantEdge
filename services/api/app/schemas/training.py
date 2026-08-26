"""Wire schemas (DTOs) for the Machine Learning Training Framework API.

The ORM models (`app/models/training.py`) stay the source of truth for
persisted shape; this module is the one place a create request is
validated and a response is assembled — the same split
`app/schemas/experiments.py` already follows.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, field_serializer

from app.models.training import TRAINING_JOB_STAGES, TRAINING_JOB_STATUSES, TRAINING_LOG_LEVELS
from app.training.base import ModelAdapterMetadata

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
    model_type: str
    hyperparameters: dict[str, Any]
    status: TrainingJobStatus
    current_stage: TrainingJobStage | None
    error_message: str | None
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
            model_type=job.model_type,
            hyperparameters=job.hyperparameters or {},
            status=job.status,  # type: ignore[arg-type]
            current_stage=job.current_stage,  # type: ignore[arg-type]
            error_message=job.error_message,
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
    hyperparameter_hints: list[str]
    version: str

    @classmethod
    def from_metadata(cls, metadata: ModelAdapterMetadata) -> "ModelAdapterDTO":
        return cls(
            name=metadata.name,
            label=metadata.label,
            description=metadata.description,
            framework=metadata.framework,
            hyperparameter_hints=list(metadata.hyperparameter_hints),
            version=metadata.version,
        )


class ModelAdapterCatalogResponse(BaseModel):
    """Every registered model adapter, for a frontend dropdown/catalogue view."""

    adapters: list[ModelAdapterDTO]


__all__ = [
    "TRAINING_LOG_LEVELS",
    "ModelAdapterCatalogResponse",
    "ModelAdapterDTO",
    "TrainingJobCreateRequest",
    "TrainingJobListResponse",
    "TrainingJobLogDTO",
    "TrainingJobResponse",
    "TrainingJobSummaryDTO",
]
