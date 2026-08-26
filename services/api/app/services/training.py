"""Training Framework service — job CRUD, lifecycle transitions, and pipeline execution.

Composes `TrainingJobRepository` the same way `ExperimentService` composes
`ExperimentRepository`: routers never touch SQL or the pipeline directly.

The "update experiment" pipeline stage is where this domain deliberately
reuses `ExperimentService` rather than writing its own experiment-mutating
SQL: a completed job moves its experiment to `status="completed"` and
records the adapter's fabricated metrics/artifact through
`ExperimentService.add_metric`/`add_artifact` — the exact same methods the
Experiment Management API itself calls, so a training run's outcome shows
up in the experiment's existing metrics/artifacts tables with zero
duplicated persistence logic.
"""

import logging
import uuid
from datetime import UTC, datetime

from app.models.training import TrainingJob, TrainingJobLog
from app.repositories.training import SORT_COLUMNS, TrainingJobFilters, TrainingJobRepository
from app.schemas.experiments import (
    ArtifactCreateRequest,
    ExperimentUpdateRequest,
    MetricCreateRequest,
)
from app.schemas.training import (
    ModelAdapterCatalogResponse,
    ModelAdapterDTO,
    TrainingJobCreateRequest,
    TrainingJobListResponse,
    TrainingJobResponse,
    TrainingJobSummaryDTO,
)
from app.services.experiments import ExperimentService
from app.training.base import TrainingDataset, TrainingResult
from app.training.errors import (
    InvalidTrainingJobSortError,
    TrainingJobNotCancellableError,
    TrainingJobNotFoundError,
)
from app.training.pipeline import TrainingPipeline
from app.training.state_machine import assert_transition_allowed

logger = logging.getLogger("app.services.training")


class TrainingJobService:
    """The one entry point routers use for every training job operation."""

    def __init__(
        self,
        repository: TrainingJobRepository,
        experiment_service: ExperimentService,
        pipeline: TrainingPipeline,
    ) -> None:
        self.repository = repository
        self.experiment_service = experiment_service
        self.pipeline = pipeline

    async def create(self, payload: TrainingJobCreateRequest) -> TrainingJobResponse:
        experiment = await self.experiment_service.get(payload.experiment_id)
        dataset_version = payload.dataset_version or experiment.dataset_version
        job = TrainingJob(
            experiment_id=payload.experiment_id,
            dataset_version=dataset_version,
            model_type=payload.model_type,
            hyperparameters=payload.hyperparameters,
        )
        created = await self.repository.create(job)
        return TrainingJobResponse.from_model(created)

    async def get(self, job_id: uuid.UUID) -> TrainingJobResponse:
        job = await self._get_or_404(job_id)
        return TrainingJobResponse.from_model(job)

    async def search(
        self,
        *,
        experiment_id: uuid.UUID | None,
        status_filter: str | None,
        model_type: str | None,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> TrainingJobListResponse:
        if sort not in SORT_COLUMNS or direction not in {"asc", "desc"}:
            raise InvalidTrainingJobSortError(sort, direction, tuple(SORT_COLUMNS))

        filters = TrainingJobFilters(
            experiment_id=experiment_id, status=status_filter, model_type=model_type
        )
        jobs, total = await self.repository.search(
            filters, sort=sort, direction=direction, limit=limit, offset=offset
        )
        return TrainingJobListResponse(
            jobs=[TrainingJobSummaryDTO.from_model(job) for job in jobs],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def delete(self, job_id: uuid.UUID) -> None:
        job = await self._get_or_404(job_id)
        if job.status == "running":
            raise TrainingJobNotCancellableError(job_id, job.status)
        await self.repository.delete(job)

    async def cancel(self, job_id: uuid.UUID) -> TrainingJobResponse:
        job = await self._get_or_404(job_id)
        assert_transition_allowed(job.status, "cancelled")
        await self._append_log(job_id, "info", None, "Job cancelled")
        # Fetched *after* the log line so the response reflects it — `add_log`
        # expires the job's `logs` collection in the session's identity map
        # (see its own docstring), so an object read before this point would
        # otherwise carry a stale/expired collection into the response.
        job = await self._get_or_404(job_id)
        updated = await self.repository.update(
            job, {"status": "cancelled", "completed_at": datetime.now(UTC)}
        )
        return TrainingJobResponse.from_model(updated)

    async def run(self, job_id: uuid.UUID) -> TrainingJobResponse:
        """Execute the training pipeline for a pending job.

        Runs synchronously within this call — no worker/queue service exists
        in this platform yet (see `AI.md` § "Machine Learning Training
        Framework"), so `POST /training-jobs/{id}/run` blocks for the
        duration of the (placeholder, near-instant) pipeline run.
        """
        job = await self._get_or_404(job_id)
        assert_transition_allowed(job.status, "running")
        job = await self.repository.update(
            job,
            {
                "status": "running",
                "current_stage": None,
                "error_message": None,
                "started_at": datetime.now(UTC),
                "completed_at": None,
            },
        )
        await self._append_log(job_id, "info", None, "Training job started")

        try:
            await self.pipeline.run(
                model_type=job.model_type,
                dataset_version=job.dataset_version,
                hyperparameters=job.hyperparameters or {},
                log=self._make_log_hook(job_id),
                load_dataset=self._load_dataset,
                save_results=self._make_save_results_hook(job_id),
                update_experiment=self._make_update_experiment_hook(job.experiment_id),
            )
        except Exception as exc:  # noqa: BLE001 - converted into a failed job, not re-raised
            failed = await self._get_or_404(job_id)
            failed = await self.repository.update(
                failed,
                {
                    "status": "failed",
                    "error_message": str(exc),
                    "completed_at": datetime.now(UTC),
                },
            )
            await self._mark_experiment_failed(job.experiment_id, str(exc))
            return TrainingJobResponse.from_model(failed)

        completed = await self._get_or_404(job_id)
        completed = await self.repository.update(
            completed, {"status": "completed", "completed_at": datetime.now(UTC)}
        )
        return TrainingJobResponse.from_model(completed)

    def list_model_adapters(self) -> ModelAdapterCatalogResponse:
        """The model adapter catalogue — the frontend's model-type dropdown source."""
        return ModelAdapterCatalogResponse(
            adapters=[
                ModelAdapterDTO.from_metadata(metadata)
                for metadata in self.pipeline.registry.describe_all()
            ]
        )

    async def _get_or_404(self, job_id: uuid.UUID) -> TrainingJob:
        job = await self.repository.get_by_id(job_id)
        if job is None:
            raise TrainingJobNotFoundError(job_id)
        return job

    async def _append_log(
        self, job_id: uuid.UUID, level: str, stage: str | None, message: str
    ) -> None:
        await self.repository.add_log(
            TrainingJobLog(job_id=job_id, level=level, stage=stage, message=message)
        )

    def _make_log_hook(self, job_id: uuid.UUID):
        async def log(stage: str, level: str, message: str) -> None:
            await self._append_log(job_id, level, stage, message)
            job = await self.repository.get_by_id(job_id)
            if job is not None:
                await self.repository.update(job, {"current_stage": stage})

        return log

    async def _load_dataset(self, dataset_version: str) -> TrainingDataset:
        """Resolve "the dataset" for a job — a citation, not real loaded rows.

        The ML Dataset Builder never persists a dataset to a table (see
        `app/training/base.py`'s `TrainingDataset` docstring), so there is
        nothing to actually read here; this stage exists to give the
        pipeline a real, named place a future real dataset-loading
        integration would plug into.
        """
        return TrainingDataset(dataset_version=dataset_version)

    def _make_save_results_hook(self, job_id: uuid.UUID):
        async def save_results(result: TrainingResult) -> None:
            job = await self.repository.get_by_id(job_id)
            if job is not None:
                await self.repository.update(
                    job,
                    {
                        "result_summary": {
                            "metrics": result.metrics,
                            "artifact_uri": result.artifact_uri,
                            **result.summary,
                        }
                    },
                )

        return save_results

    def _make_update_experiment_hook(self, experiment_id: uuid.UUID):
        async def update_experiment(result: TrainingResult) -> None:
            await self.experiment_service.update(
                experiment_id, ExperimentUpdateRequest(status="completed")
            )
            for name, value in result.metrics.items():
                await self.experiment_service.add_metric(
                    experiment_id, MetricCreateRequest(name=name, value=value)
                )
            await self.experiment_service.add_artifact(
                experiment_id,
                ArtifactCreateRequest(
                    artifact_type="model_checkpoint",
                    uri=result.artifact_uri,
                    description="Recorded automatically by the Training Framework.",
                ),
            )

        return update_experiment

    async def _mark_experiment_failed(self, experiment_id: uuid.UUID, error_message: str) -> None:
        try:
            await self.experiment_service.update(
                experiment_id, ExperimentUpdateRequest(status="failed")
            )
        except Exception:  # noqa: BLE001 - best-effort; the job's own failure is already recorded
            logger.exception(
                "Failed to mark experiment %s as failed after a training job error: %s",
                experiment_id,
                error_message,
            )
