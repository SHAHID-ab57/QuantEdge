"""Wire schemas (DTOs) for the Experiment Management API.

The ORM models (`app/models/experiment.py`) stay the source of truth for
persisted shape; this module is the one place they're mapped onto the wire
and the one place a create/update request is validated — the same
Pydantic-free-engine / Pydantic-DTO split every other domain in this
codebase follows (see `app/schemas/features.py`, `app/schemas/ml_datasets.py`).
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, field_serializer

from app.models.experiment import ARTIFACT_TYPES, EXPERIMENT_STATUSES

if TYPE_CHECKING:
    from app.models.experiment import Experiment, ExperimentArtifact, ExperimentMetric

ExperimentStatus = Literal["draft", "running", "completed", "failed", "archived"]
ArtifactType = Literal["dataset_export", "model_checkpoint", "report", "plot", "other"]


def _iso(value: datetime) -> str:
    """ISO-8601 UTC with a literal `Z`, matching every timestamp on this API."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _feature_set_dto(raw: list[dict] | None) -> "list[FeatureRequestDTO] | None":
    """Reconstruct typed feature-request DTOs from the ORM's raw JSON column."""
    return None if raw is None else [FeatureRequestDTO(**item) for item in raw]


def _target_config_dto(raw: list[dict] | None) -> "list[TargetRequestDTO] | None":
    """Reconstruct typed target-request DTOs from the ORM's raw JSON column."""
    return None if raw is None else [TargetRequestDTO(**item) for item in raw]


def _split_config_dto(raw: dict | None) -> "SplitConfigDTO | None":
    """Reconstruct a typed split-config DTO from the ORM's raw JSON column."""
    return None if raw is None else SplitConfigDTO(**raw)


class FeatureRequestDTO(BaseModel):
    """One feature this experiment's dataset was built with — mirrors `FeatureRequestBody`."""

    feature: str
    params: dict[str, str] = Field(default_factory=dict)


class TargetRequestDTO(BaseModel):
    """One prediction target this experiment's dataset used — mirrors `MLTargetRequestItem`."""

    target: str
    params: dict[str, str] = Field(default_factory=dict)


class SplitConfigDTO(BaseModel):
    """The train/validation/test split ratios this experiment's dataset used."""

    train: float = Field(ge=0.0, le=1.0)
    validation: float = Field(ge=0.0, le=1.0)
    test: float = Field(ge=0.0, le=1.0)


class ExperimentCreateRequest(BaseModel):
    """A new experiment registration."""

    name: str = Field(..., min_length=1, max_length=200)
    dataset_version: str | None = Field(
        default=None,
        max_length=200,
        description="The ml_dataset_id (or dataset_id) this experiment was built over.",
    )
    feature_set: list[FeatureRequestDTO] | None = None
    target_config: list[TargetRequestDTO] | None = None
    split_config: SplitConfigDTO | None = None
    model_type: str | None = Field(
        default=None,
        max_length=100,
        description="A placeholder label only — no training engine exists yet.",
    )
    status: ExperimentStatus = "draft"
    notes: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=32)


class ExperimentUpdateRequest(BaseModel):
    """A partial update — every field is optional; only fields actually sent are applied."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    dataset_version: str | None = Field(default=None, max_length=200)
    feature_set: list[FeatureRequestDTO] | None = None
    target_config: list[TargetRequestDTO] | None = None
    split_config: SplitConfigDTO | None = None
    model_type: str | None = Field(default=None, max_length=100)
    status: ExperimentStatus | None = None
    notes: str | None = None
    tags: list[str] | None = Field(default=None, max_length=32)


class MetricCreateRequest(BaseModel):
    """One evaluation metric to record against an experiment."""

    name: str = Field(..., min_length=1, max_length=100)
    value: float
    unit: str | None = Field(default=None, max_length=32)


class ArtifactCreateRequest(BaseModel):
    """One artifact reference to record against an experiment."""

    artifact_type: ArtifactType
    uri: str = Field(..., min_length=1, max_length=1024)
    description: str | None = None


class MetricDTO(BaseModel):
    id: str
    name: str
    value: float
    unit: str | None
    recorded_at: datetime

    @field_serializer("recorded_at")
    def _serialize_recorded_at(self, value: datetime) -> str:
        return _iso(value)

    @classmethod
    def from_model(cls, metric: "ExperimentMetric") -> "MetricDTO":
        return cls(
            id=str(metric.id),
            name=metric.name,
            value=metric.value,
            unit=metric.unit,
            recorded_at=metric.recorded_at,
        )


class ArtifactDTO(BaseModel):
    id: str
    artifact_type: ArtifactType
    uri: str
    description: str | None
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return _iso(value)

    @classmethod
    def from_model(cls, artifact: "ExperimentArtifact") -> "ArtifactDTO":
        return cls(
            id=str(artifact.id),
            artifact_type=artifact.artifact_type,  # type: ignore[arg-type]
            uri=artifact.uri,
            description=artifact.description,
            created_at=artifact.created_at,
        )


class ExperimentResponse(BaseModel):
    """A full experiment record — metadata plus its metrics and artifact references."""

    id: str
    name: str
    dataset_version: str | None
    feature_set: list[FeatureRequestDTO] | None
    target_config: list[TargetRequestDTO] | None
    split_config: SplitConfigDTO | None
    model_type: str | None
    status: ExperimentStatus
    notes: str | None
    tags: list[str]
    metrics: list[MetricDTO]
    artifacts: list[ArtifactDTO]
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_timestamps(self, value: datetime) -> str:
        return _iso(value)

    @classmethod
    def from_model(cls, experiment: "Experiment") -> "ExperimentResponse":
        return cls(
            id=str(experiment.id),
            name=experiment.name,
            dataset_version=experiment.dataset_version,
            feature_set=_feature_set_dto(experiment.feature_set),
            target_config=_target_config_dto(experiment.target_config),
            split_config=_split_config_dto(experiment.split_config),
            model_type=experiment.model_type,
            status=experiment.status,  # type: ignore[arg-type]
            notes=experiment.notes,
            tags=sorted(tag.tag for tag in experiment.tags),
            metrics=[MetricDTO.from_model(metric) for metric in experiment.metrics],
            artifacts=[ArtifactDTO.from_model(artifact) for artifact in experiment.artifacts],
            created_at=experiment.created_at,
            updated_at=experiment.updated_at,
        )


class ExperimentSummaryDTO(BaseModel):
    """One row in the experiment list — metadata only, to keep a list page light."""

    id: str
    name: str
    dataset_version: str | None
    model_type: str | None
    status: ExperimentStatus
    tags: list[str]
    metric_count: int
    artifact_count: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_timestamps(self, value: datetime) -> str:
        return _iso(value)

    @classmethod
    def from_model(cls, experiment: "Experiment") -> "ExperimentSummaryDTO":
        return cls(
            id=str(experiment.id),
            name=experiment.name,
            dataset_version=experiment.dataset_version,
            model_type=experiment.model_type,
            status=experiment.status,  # type: ignore[arg-type]
            tags=sorted(tag.tag for tag in experiment.tags),
            metric_count=len(experiment.metrics),
            artifact_count=len(experiment.artifacts),
            created_at=experiment.created_at,
            updated_at=experiment.updated_at,
        )


class ExperimentListResponse(BaseModel):
    """One page of experiments plus the metadata a list UI needs to paginate."""

    experiments: list[ExperimentSummaryDTO]
    total: int
    limit: int
    offset: int
    statuses: list[str] = Field(
        default_factory=lambda: list(EXPERIMENT_STATUSES),
        description="Every valid experiment status, for a filter dropdown.",
    )
    artifact_types: list[str] = Field(
        default_factory=lambda: list(ARTIFACT_TYPES),
        description="Every valid artifact type, for an artifact-type filter dropdown.",
    )
