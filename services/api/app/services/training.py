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
from pathlib import Path

from app.features.ai_extensions import NormalizationStats
from app.models.training import TrainingJob, TrainingJobLog
from app.repositories.training import SORT_COLUMNS, TrainingJobFilters, TrainingJobRepository
from app.schemas.experiments import (
    ArtifactCreateRequest,
    ArtifactType,
    ExperimentUpdateRequest,
    MetricCreateRequest,
)
from app.schemas.features import FeatureRequestItem
from app.schemas.ml_datasets import MLDatasetRequest, MLTargetRequestItem
from app.schemas.training import (
    ModelAdapterCatalogResponse,
    ModelAdapterDTO,
    TrainingArtifactDTO,
    TrainingArtifactListResponse,
    TrainingJobCreateRequest,
    TrainingJobListResponse,
    TrainingJobPredictResponse,
    TrainingJobResponse,
    TrainingJobSummaryDTO,
)
from app.services.experiments import ExperimentService
from app.services.ml_datasets import MLDatasetService
from app.training.base import TrainingDataset, TrainingResult
from app.training.dataset_loader import build_training_dataset
from app.training.error_reporting import describe_training_failure
from app.training.errors import (
    InvalidPredictionInputError,
    InvalidTrainingJobSortError,
    MissingFeatureOrTargetConfigError,
    MissingTrainingDataSourceError,
    PredictionExecutionError,
    PredictionNotAvailableError,
    TrainingArtifactNotFoundError,
    TrainingJobNotCancellableError,
    TrainingJobNotFoundError,
)
from app.training.interpretability import confidence_level
from app.training.normalization import DEFAULT_NORMALIZATION_METHOD, apply_normalization
from app.training.pipeline import TrainingPipeline
from app.training.state_machine import assert_transition_allowed

logger = logging.getLogger("app.services.training")

#: Maps a training-run artifact type (`app/training/artifact_files.py`'s output keys)
#: onto one of `Experiment`'s own fixed artifact categories
#: (`dataset_export | model_checkpoint | report | plot | other`,
#: DB-CHECK-constrained in `app/models/experiment.py`) — never a new category.
_EXPERIMENT_ARTIFACT_CATEGORY: dict[str, ArtifactType] = {
    "metrics_json": "report",
    "training_report_json": "report",
    "feature_importance_csv": "report",
    "confusion_matrix_png": "plot",
    "roc_curve_png": "plot",
    "precision_recall_curve_png": "plot",
}


class TrainingJobService:
    """The one entry point routers use for every training job operation."""

    def __init__(
        self,
        repository: TrainingJobRepository,
        experiment_service: ExperimentService,
        pipeline: TrainingPipeline,
        ml_dataset_service: MLDatasetService,
    ) -> None:
        self.repository = repository
        self.experiment_service = experiment_service
        self.pipeline = pipeline
        self.ml_dataset_service = ml_dataset_service

    async def create(self, payload: TrainingJobCreateRequest) -> TrainingJobResponse:
        experiment = await self.experiment_service.get(payload.experiment_id)
        dataset_version = payload.dataset_version or experiment.dataset_version
        job = TrainingJob(
            experiment_id=payload.experiment_id,
            dataset_version=dataset_version,
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            target_column=payload.target_column,
            model_type=payload.model_type,
            hyperparameters=payload.hyperparameters,
            normalize_features=payload.normalize_features,
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
                load_dataset=self._make_load_dataset_hook(job),
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
                    "error_detail": describe_training_failure(exc),
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

    async def predict(
        self, job_id: uuid.UUID, rows: list[list[float]]
    ) -> TrainingJobPredictResponse:
        """Predict for `rows` using a completed job's serialized model.

        Loads the model back from `artifact_uri` (never reuses in-memory
        state from the training run — see `ModelAdapter.predict`'s own
        docstring), so this works even long after the job finished, in a
        different process or request.
        """
        job = await self._get_or_404(job_id)
        summary = job.result_summary or {}
        artifact_uri = summary.get("artifact_uri")
        if job.status != "completed" or not artifact_uri:
            raise PredictionNotAvailableError(job_id, job.status)

        feature_columns = summary.get("feature_columns")
        if feature_columns is not None and any(len(row) != len(feature_columns) for row in rows):
            raise InvalidPredictionInputError(len(feature_columns))

        rows_to_predict = self._normalize_prediction_rows(summary, rows)

        adapter = self.pipeline.registry.get(job.model_type)
        try:
            predictions = adapter.predict(artifact_uri, rows_to_predict)
            probabilities = adapter.predict_proba(artifact_uri, rows_to_predict)
        except Exception as exc:  # noqa: BLE001 - surfaced as a named domain error
            raise PredictionExecutionError(job.model_type, f"{type(exc).__name__}: {exc}") from exc

        classes = summary.get("classes") if probabilities is not None else None
        confidence_levels = (
            [confidence_level(max(row)) for row in probabilities]
            if probabilities is not None
            else None
        )

        return TrainingJobPredictResponse(
            predictions=predictions,
            feature_columns=feature_columns,
            classes=classes,
            probabilities=probabilities,
            confidence_levels=confidence_levels,
        )

    def _normalize_prediction_rows(
        self, summary: dict[str, object], rows: list[list[float]]
    ) -> list[list[float]]:
        """Apply the identical transform this job trained with, if any.

        `summary["normalization"]` is `None` for a job trained with
        `normalize_features=False` (or the placeholder adapter, which never
        sets it at all) — `rows` pass through unchanged in that case.
        Reconstructs `NormalizationStats` from the plain-dict shape
        `normalization_stats_to_dicts` recorded them in, so a prediction on
        raw, human-scale input is transformed exactly the way training data
        was before ever reaching the model — predicting on unnormalized
        input against a model fit on normalized input would otherwise be
        silently wrong.
        """
        raw_stats = summary.get("normalization")
        if not raw_stats:
            return rows
        stats = [NormalizationStats(**entry) for entry in raw_stats]  # type: ignore[arg-type]
        method = summary.get("normalization_method") or DEFAULT_NORMALIZATION_METHOD
        return apply_normalization(rows, stats, method=method)  # type: ignore[arg-type]

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

    def _make_load_dataset_hook(self, job: TrainingJob):
        async def load_dataset(dataset_version: str) -> TrainingDataset:
            """Resolve "the dataset" for a job.

            For a placeholder-style adapter (`requires_real_data=False`),
            this is a citation only — the ML Dataset Builder never persists
            a dataset to a table (see `app/training/base.py`'s
            `TrainingDataset` docstring), so there is nothing to actually
            read. For a `requires_real_data` adapter, this actually builds
            a real `MLDataset` by reusing `MLDatasetService` (the exact
            same service `/markets/{symbol}/ml/dataset` itself calls) with
            the linked experiment's own recorded `feature_set`/
            `target_config`/`split_config` — never a second dataset-
            building path.
            """
            adapter = self.pipeline.registry.get(job.model_type)
            if not adapter.metadata.requires_real_data:
                return TrainingDataset(dataset_version=dataset_version)

            if not job.symbol or not job.timeframe:
                raise MissingTrainingDataSourceError()

            experiment = await self.experiment_service.get(job.experiment_id)
            if not experiment.feature_set or not experiment.target_config:
                raise MissingFeatureOrTargetConfigError()

            split = experiment.split_config
            request = MLDatasetRequest(
                timeframe=job.timeframe,
                features=[
                    FeatureRequestItem(feature=item.feature, params=item.params)
                    for item in experiment.feature_set
                ],
                targets=[
                    MLTargetRequestItem(target=item.target, params=item.params)
                    for item in experiment.target_config
                ],
                split_train=split.train if split else 0.7,
                split_validation=split.validation if split else 0.15,
                split_test=split.test if split else 0.15,
            )
            ml_dataset = await self.ml_dataset_service.build_ml_dataset(job.symbol, request)
            return build_training_dataset(
                ml_dataset,
                model_kind=adapter.metadata.model_kind,
                target_column=job.target_column,
                normalize=job.normalize_features,
            )

        return load_dataset

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
            # A real adapter (`requires_real_data=True`) additionally records its
            # interpretability/evaluation report artifacts (metrics.json,
            # training_report.json, feature_importance.csv, and — for a classifier —
            # confusion_matrix.png/roc_curve.png/precision_recall_curve.png; see
            # `app/training/artifact_files.py`) through this same `add_artifact` call,
            # one per entry — the placeholder adapter records none, since
            # `result.summary` never has an "artifacts" key for it. `artifact_type`
            # here must still be one of `Experiment`'s own fixed, DB-CHECK-constrained
            # categories (`app/models/experiment.py`) — never a new one — so each
            # training-produced file maps onto the closest existing category
            # (`_EXPERIMENT_ARTIFACT_CATEGORY`) and keeps its specific identity in
            # `description` instead.
            for artifact_type, uri in (result.summary.get("artifacts") or {}).items():
                await self.experiment_service.add_artifact(
                    experiment_id,
                    ArtifactCreateRequest(
                        artifact_type=_EXPERIMENT_ARTIFACT_CATEGORY.get(artifact_type, "other"),
                        uri=uri,
                        description=(
                            f"Recorded automatically by the Training Framework ({artifact_type})."
                        ),
                    ),
                )

        return update_experiment

    async def list_artifacts(self, job_id: uuid.UUID) -> TrainingArtifactListResponse:
        """Every downloadable artifact a completed job's training run produced."""
        job = await self._get_or_404(job_id)
        summary = job.result_summary or {}
        entries: list[TrainingArtifactDTO] = []
        artifact_uri = summary.get("artifact_uri")
        if artifact_uri:
            entries.append(TrainingArtifactDTO.build(job_id, "model_joblib", artifact_uri))
        for artifact_type, uri in (summary.get("artifacts") or {}).items():
            entries.append(TrainingArtifactDTO.build(job_id, artifact_type, uri))
        return TrainingArtifactListResponse(job_id=str(job_id), artifacts=entries)

    async def get_artifact_file(self, job_id: uuid.UUID, artifact_type: str) -> tuple[Path, str]:
        """Resolve one artifact type to a local file path and content type, for download."""
        job = await self._get_or_404(job_id)
        summary = job.result_summary or {}
        if artifact_type == "model_joblib":
            uri = summary.get("artifact_uri")
        else:
            uri = (summary.get("artifacts") or {}).get(artifact_type)
        if not uri or not isinstance(uri, str) or not uri.startswith("file://"):
            raise TrainingArtifactNotFoundError(job_id, artifact_type)
        path = Path.from_uri(uri)
        if not path.exists():
            raise TrainingArtifactNotFoundError(job_id, artifact_type)
        return path, TrainingArtifactDTO.build(job_id, artifact_type, uri).content_type

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
