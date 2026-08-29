"""Benchmark comparison — several already-completed training jobs, one metric
table.

Framework-free and database-free, mirroring every other engine on this
platform: this module knows nothing about SQLAlchemy or `TrainingJob`; the
service layer (`app/services/evaluation.py`) is the one place a database
session exists, and maps rows onto `BenchmarkCandidate` before calling
`compare` here. This is a **read-only comparison over data that already
exists** — a completed `TrainingJob`'s `result_summary.metrics` (itself
copied onto its `Experiment` by the unchanged `_make_update_experiment_hook`)
— not a new place metrics get computed or stored.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.evaluation.registry import MetricRegistry


@dataclass(frozen=True, slots=True)
class BenchmarkCandidate:
    """One completed training job's identity and recorded metrics.

    Every field below is read from data a training job already produced —
    nothing here is computed by this module. `symbol`/`timeframe`/
    `feature_count`/`sample_count` back the frontend's Dataset Summary Card;
    `model_artifact_url` is the same deterministic download path
    `TrainingArtifactDTO.build` already computes for the Artifact Management
    panel; `report` is the job's own `result_summary` dict verbatim, letting
    the frontend reuse its existing `EvaluationSummary` component (confusion
    matrix, ROC/PR curves, feature importance, prediction samples) for one
    candidate's full detail without this engine recomputing any of it.
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
    report: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BenchmarkBestEntry:
    """The winning candidate for one metric, across every candidate compared."""

    metric: str
    training_job_id: str
    model_type: str
    value: float
    higher_is_better: bool


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """A full comparison: every candidate, plus the best one per metric."""

    candidates: list[BenchmarkCandidate]
    best_by_metric: list[BenchmarkBestEntry]


def compare(
    candidates: list[BenchmarkCandidate], metric_registry: MetricRegistry
) -> BenchmarkResult:
    """Compare `candidates`, picking a winner per metric name that appears on
    at least one of them.

    A metric name not found in `metric_registry` (e.g. one recorded by a
    metric that has since been removed, or a custom name a future adapter
    invented) still gets a "best" entry — this falls back to
    `higher_is_better=True` rather than excluding it, since a silently
    dropped metric would be a worse outcome than a documented, conservative
    assumption. `MetricMetadata.higher_is_better` is used whenever the name
    *is* still registered.
    """
    metric_names = sorted({name for candidate in candidates for name in candidate.metrics})

    best_by_metric: list[BenchmarkBestEntry] = []
    for name in metric_names:
        higher_is_better = True
        if metric_registry.has(name):
            higher_is_better = metric_registry.get(name).metadata.higher_is_better

        scored = [
            (candidate, candidate.metrics[name])
            for candidate in candidates
            if name in candidate.metrics
        ]
        if not scored:
            continue
        chooser = max if higher_is_better else min
        best_candidate, best_value = chooser(scored, key=lambda pair: pair[1])
        best_by_metric.append(
            BenchmarkBestEntry(
                metric=name,
                training_job_id=best_candidate.training_job_id,
                model_type=best_candidate.model_type,
                value=best_value,
                higher_is_better=higher_is_better,
            )
        )

    return BenchmarkResult(candidates=candidates, best_by_metric=best_by_metric)
