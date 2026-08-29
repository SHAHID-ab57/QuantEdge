"""Model Evaluation & Benchmarking service — the metric catalogue, the
benchmark comparison workflow, and Benchmark History.

Composes `TrainingJobRepository` and `ExperimentService` the same way
`TrainingJobService` already does — this service adds no new table for the
comparison itself and no new place metrics get computed: a benchmark is a
**read-only comparison** over `TrainingJob.result_summary["metrics"]`,
already written by `TrainingJobService._make_save_results_hook`, for jobs
whose `status` reached `"completed"`. `app/evaluation/benchmark.py` does the
actual comparison; this module's only job is resolving which `TrainingJob`
rows qualify, mapping them onto `BenchmarkCandidate` (reusing already-computed
fields — nothing here recomputes a metric, a confusion matrix, or an ROC
curve), and — the one genuinely new persistence in this module — recording
each benchmark request/response to Benchmark History, the same best-effort
"record it, never let bookkeeping sink the primary outcome" pattern
`MLDatasetService._record_build` already established.
"""

import logging
import uuid

from app.evaluation.base import Metric
from app.evaluation.benchmark import BenchmarkCandidate, compare
from app.evaluation.errors import (
    BenchmarkRunNotFoundError,
    EmptyBenchmarkError,
    InvalidBenchmarkRunSortError,
    NoBenchmarkTargetError,
)
from app.evaluation.registry import MetricRegistry
from app.models.evaluation_benchmark_run import EvaluationBenchmarkRun
from app.repositories.evaluation_benchmark_runs import (
    SORT_COLUMNS as BENCHMARK_RUN_SORT_COLUMNS,
)
from app.repositories.evaluation_benchmark_runs import (
    EvaluationBenchmarkRunFilters,
    EvaluationBenchmarkRunRepository,
)
from app.repositories.training import TrainingJobFilters, TrainingJobRepository
from app.schemas.evaluation import (
    BenchmarkBestEntryDTO,
    BenchmarkCandidateDTO,
    BenchmarkRequest,
    BenchmarkResponse,
    BenchmarkRunDetailResponse,
    BenchmarkRunListResponse,
    BenchmarkRunSummaryDTO,
    MetricCatalogResponse,
    MetricMetadataDTO,
)
from app.schemas.training import TrainingArtifactDTO
from app.services.experiments import ExperimentService
from app.training.registry import ModelAdapterRegistry

logger = logging.getLogger("app.services.evaluation")


class EvaluationService:
    """The one entry point routers use for every evaluation/benchmark operation."""

    def __init__(
        self,
        training_repository: TrainingJobRepository,
        experiment_service: ExperimentService,
        metric_registry: MetricRegistry,
        model_adapter_registry: ModelAdapterRegistry,
        benchmark_run_repository: EvaluationBenchmarkRunRepository,
        *,
        benchmark_max_candidates: int,
        history_default_limit: int = 20,
        history_max_limit: int = 100,
    ) -> None:
        self.training_repository = training_repository
        self.experiment_service = experiment_service
        self.metric_registry = metric_registry
        self.model_adapter_registry = model_adapter_registry
        self.benchmark_run_repository = benchmark_run_repository
        self.benchmark_max_candidates = benchmark_max_candidates
        self.history_default_limit = history_default_limit
        self.history_max_limit = history_max_limit

    def list_metrics(self) -> MetricCatalogResponse:
        """The full registered metric catalogue — classification and regression."""
        return MetricCatalogResponse(
            metrics=[
                MetricMetadataDTO.from_metadata(metric.metadata)
                for metric in _sorted(self.metric_registry)
            ]
        )

    async def benchmark(self, request: BenchmarkRequest) -> BenchmarkResponse:
        """Compare every completed training job matching `request`.

        Raises `NoBenchmarkTargetError` if the request names nothing to
        match on, and `EmptyBenchmarkError` if the match is well-formed but
        matches zero completed jobs — a benchmark table with zero rows is
        never a useful response. A successful comparison is also recorded to
        Benchmark History (best-effort — see `_record_benchmark_run`).
        """
        if not (request.dataset_version or request.target_column or request.experiment_ids):
            raise NoBenchmarkTargetError()

        filters = TrainingJobFilters(
            status="completed",
            dataset_version=request.dataset_version,
            target_column=request.target_column,
        )
        jobs, _total = await self.training_repository.search(
            filters,
            sort="completed_at",
            direction="desc",
            limit=self.benchmark_max_candidates,
            offset=0,
        )
        if request.experiment_ids:
            wanted = set(request.experiment_ids)
            jobs = [job for job in jobs if job.experiment_id in wanted]

        experiment_names: dict[uuid.UUID, str] = {}
        candidates: list[BenchmarkCandidate] = []
        for job in jobs:
            summary = job.result_summary or {}
            metrics = summary.get("metrics") or {}
            if not metrics:
                # A completed job with no recorded metrics (e.g. the
                # `placeholder` adapter, or one that never reached
                # `update_experiment`) has nothing to compare — excluded
                # rather than shown as an all-empty row.
                continue

            if job.experiment_id not in experiment_names:
                experiment = await self.experiment_service.get(job.experiment_id)
                experiment_names[job.experiment_id] = experiment.name

            model_kind = "unknown"
            if self.model_adapter_registry.has(job.model_type):
                model_kind = self.model_adapter_registry.get(job.model_type).metadata.model_kind

            # `model_metadata` (feature_count/sample_count) and `artifact_uri`
            # were already computed and recorded by the training run itself
            # (`app/training/model_metadata.py`'s `collect_model_metadata`,
            # `ModelSerializer.save`) — read here, never recomputed. The
            # artifact URL is the exact same deterministic path
            # `TrainingArtifactDTO.build` already gives the Artifact
            # Management panel for the identical (job_id, "model_joblib")
            # pair, so a benchmark row's "download model" link and that
            # panel's own link always agree.
            model_metadata = summary.get("model_metadata") or {}
            artifact_uri = summary.get("artifact_uri")
            model_artifact_url = (
                TrainingArtifactDTO.build(job.id, "model_joblib", artifact_uri).download_url
                if artifact_uri
                else None
            )

            candidates.append(
                BenchmarkCandidate(
                    training_job_id=str(job.id),
                    experiment_id=str(job.experiment_id),
                    experiment_name=experiment_names[job.experiment_id],
                    model_type=job.model_type,
                    model_kind=model_kind,
                    dataset_version=job.dataset_version,
                    target_column=job.target_column,
                    completed_at=job.completed_at,
                    metrics=metrics,
                    symbol=job.symbol,
                    timeframe=job.timeframe,
                    feature_count=model_metadata.get("feature_count"),
                    sample_count=model_metadata.get("sample_count"),
                    model_artifact_url=model_artifact_url,
                    report=summary,
                )
            )

        if not candidates:
            raise EmptyBenchmarkError()

        result = compare(candidates, self.metric_registry)
        response = BenchmarkResponse(
            candidates=[BenchmarkCandidateDTO.from_candidate(c) for c in result.candidates],
            best_by_metric=[BenchmarkBestEntryDTO.from_entry(e) for e in result.best_by_metric],
        )
        await self._record_benchmark_run(request, response)
        return response

    async def list_benchmark_runs(
        self,
        *,
        dataset_version: str | None,
        target_column: str | None,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> BenchmarkRunListResponse:
        """Benchmark History's list view — every past run this session recorded, paginated."""
        if sort not in BENCHMARK_RUN_SORT_COLUMNS or direction not in {"asc", "desc"}:
            raise InvalidBenchmarkRunSortError(sort, direction, tuple(BENCHMARK_RUN_SORT_COLUMNS))

        filters = EvaluationBenchmarkRunFilters(
            dataset_version=dataset_version, target_column=target_column
        )
        runs, total = await self.benchmark_run_repository.search(
            filters, sort=sort, direction=direction, limit=limit, offset=offset
        )
        return BenchmarkRunListResponse(
            runs=[BenchmarkRunSummaryDTO.from_model(run) for run in runs],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_benchmark_run(self, run_id: uuid.UUID) -> BenchmarkRunDetailResponse:
        """One past benchmark run's full record — Benchmark History's reopen view."""
        run = await self.benchmark_run_repository.get_by_id(run_id)
        if run is None:
            raise BenchmarkRunNotFoundError(run_id)
        return BenchmarkRunDetailResponse.from_model(run)

    async def delete_benchmark_run(self, run_id: uuid.UUID) -> None:
        """Remove one past run from Benchmark History.

        The underlying training jobs are untouched.
        """
        run = await self.benchmark_run_repository.get_by_id(run_id)
        if run is None:
            raise BenchmarkRunNotFoundError(run_id)
        await self.benchmark_run_repository.delete(run)

    async def _record_benchmark_run(
        self, request: BenchmarkRequest, response: BenchmarkResponse
    ) -> None:
        """Persist one `benchmark` call to Benchmark History.

        Best-effort: a failure here must never fail the comparison itself
        (the researcher already has their result on screen) — logged and
        swallowed, matching `MLDatasetService._record_build`'s own
        precedent for the identical situation.
        """
        try:
            await self.benchmark_run_repository.create(
                EvaluationBenchmarkRun(
                    dataset_version=request.dataset_version,
                    target_column=request.target_column,
                    candidate_count=len(response.candidates),
                    request=request.model_dump(mode="json"),
                    response=response.model_dump(mode="json"),
                )
            )
        except Exception:  # noqa: BLE001 - best-effort; the comparison itself already succeeded
            logger.exception("Failed to record benchmark run to Benchmark History")


def _sorted(registry: MetricRegistry) -> list[Metric]:
    """`MetricRegistry` already iterates in sorted-name order — a thin,
    named wrapper only so `list_metrics` reads as intent, not iteration."""
    return list(registry)
