"""Wire schemas (DTOs) for the Model Evaluation & Benchmarking Engine API.

Same split as every other domain on this platform: `app/evaluation/` stays
framework/database-free, and this module is the one place a benchmark
request is validated and a response is assembled.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_serializer

from app.evaluation.base import MetricCategory

if TYPE_CHECKING:
    from app.evaluation.base import MetricMetadata
    from app.evaluation.benchmark import BenchmarkBestEntry, BenchmarkCandidate
    from app.models.evaluation_benchmark_run import EvaluationBenchmarkRun


def _iso(value: datetime) -> str:
    """ISO-8601 UTC with a literal `Z`, matching every timestamp on this API."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class MetricMetadataDTO(BaseModel):
    """One registered metric's catalogue entry — no computed value, just its shape."""

    name: str
    label: str
    description: str
    category: MetricCategory
    higher_is_better: bool
    requires_probabilities: bool
    version: str

    @classmethod
    def from_metadata(cls, metadata: "MetricMetadata") -> "MetricMetadataDTO":
        return cls(
            name=metadata.name,
            label=metadata.label,
            description=metadata.description,
            category=metadata.category,
            higher_is_better=metadata.higher_is_better,
            requires_probabilities=metadata.requires_probabilities,
            version=metadata.version,
        )


class MetricCatalogResponse(BaseModel):
    """Every registered metric, classification and regression alike."""

    metrics: list[MetricMetadataDTO]


class BenchmarkRequest(BaseModel):
    """Which completed training jobs to compare.

    At least one of `dataset_version`, `target_column`, or `experiment_ids`
    must be given — otherwise every completed job on the platform would
    match, which is never actually what "compare these models" means.
    `experiment_ids`, when given, narrows the match further (an intersection,
    not an alternative) — the same "every given filter narrows" contract
    `TrainingJobFilters` already has for every other field.
    """

    dataset_version: str | None = Field(
        default=None,
        max_length=200,
        description="Only compare jobs trained over this dataset citation",
    )
    target_column: str | None = Field(
        default=None,
        max_length=100,
        description="Only compare jobs predicting this target column",
    )
    experiment_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Only compare jobs belonging to one of these experiments",
    )


class BenchmarkCandidateDTO(BaseModel):
    """One completed training job's identity and recorded metrics, for one row
    of a benchmark comparison table.

    `symbol`/`timeframe`/`feature_count`/`sample_count` back the frontend's
    Dataset Summary Card; `model_artifact_url` and `experiment_id` back its
    deep links (Experiment, Training Job, Model Artifact); `report` is the
    job's own `result_summary` dict, verbatim, letting the frontend reuse its
    existing `EvaluationSummary` component (confusion matrix, ROC/PR curves,
    feature importance, prediction samples) for this one candidate's full
    detail — nothing here is recomputed, only passed through.
    """

    training_job_id: str
    experiment_id: str
    experiment_name: str
    model_type: str
    model_kind: str
    dataset_version: str | None
    target_column: str | None
    completed_at: datetime | None
    metrics: dict[str, float]
    symbol: str | None = None
    timeframe: str | None = None
    feature_count: int | None = None
    sample_count: int | None = None
    model_artifact_url: str | None = None
    report: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("completed_at")
    def _serialize_completed_at(self, value: datetime | None) -> str | None:
        return None if value is None else _iso(value)

    @classmethod
    def from_candidate(cls, candidate: "BenchmarkCandidate") -> "BenchmarkCandidateDTO":
        return cls(
            training_job_id=candidate.training_job_id,
            experiment_id=candidate.experiment_id,
            experiment_name=candidate.experiment_name,
            model_type=candidate.model_type,
            model_kind=candidate.model_kind,
            dataset_version=candidate.dataset_version,
            target_column=candidate.target_column,
            completed_at=candidate.completed_at,
            metrics=candidate.metrics,
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            feature_count=candidate.feature_count,
            sample_count=candidate.sample_count,
            model_artifact_url=candidate.model_artifact_url,
            report=candidate.report,
        )


class BenchmarkBestEntryDTO(BaseModel):
    """The winning candidate for one metric, across every candidate compared."""

    metric: str
    training_job_id: str
    model_type: str
    value: float
    higher_is_better: bool

    @classmethod
    def from_entry(cls, entry: "BenchmarkBestEntry") -> "BenchmarkBestEntryDTO":
        return cls(
            metric=entry.metric,
            training_job_id=entry.training_job_id,
            model_type=entry.model_type,
            value=entry.value,
            higher_is_better=entry.higher_is_better,
        )


class BenchmarkResponse(BaseModel):
    """A full benchmark comparison: every matched candidate, plus the best
    one per metric — the frontend's model comparison table and "best model"
    summary read directly off this."""

    candidates: list[BenchmarkCandidateDTO]
    best_by_metric: list[BenchmarkBestEntryDTO]


class BenchmarkRunSummaryDTO(BaseModel):
    """One row in Benchmark History's list — metadata only, to keep the list light.

    Mirrors `MLDatasetBuildSummaryDTO`'s own "list is metadata-only, detail is
    the full record" split.
    """

    id: str
    dataset_version: str | None
    target_column: str | None
    candidate_count: int
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return _iso(value)

    @classmethod
    def from_model(cls, run: "EvaluationBenchmarkRun") -> "BenchmarkRunSummaryDTO":
        return cls(
            id=str(run.id),
            dataset_version=run.dataset_version,
            target_column=run.target_column,
            candidate_count=run.candidate_count,
            created_at=run.created_at,
        )


class BenchmarkRunListResponse(BaseModel):
    """One page of past benchmark runs — Benchmark History's list view."""

    runs: list[BenchmarkRunSummaryDTO]
    total: int
    limit: int
    offset: int


class BenchmarkRunDetailResponse(BaseModel):
    """One persisted benchmark run's full record — the exact request and
    response it produced, reopened."""

    id: str
    created_at: datetime
    request: BenchmarkRequest
    response: BenchmarkResponse

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return _iso(value)

    @classmethod
    def from_model(cls, run: "EvaluationBenchmarkRun") -> "BenchmarkRunDetailResponse":
        return cls(
            id=str(run.id),
            created_at=run.created_at,
            request=BenchmarkRequest.model_validate(run.request),
            response=BenchmarkResponse.model_validate(run.response),
        )


__all__ = [
    "BenchmarkBestEntryDTO",
    "BenchmarkCandidateDTO",
    "BenchmarkRequest",
    "BenchmarkResponse",
    "BenchmarkRunDetailResponse",
    "BenchmarkRunListResponse",
    "BenchmarkRunSummaryDTO",
    "MetricCatalogResponse",
    "MetricMetadataDTO",
]
