"""The training pipeline: a fixed six-stage orchestration.

    validate dataset -> load dataset -> initialize model -> execute training
        -> save results -> update experiment

Framework-free by design, the same way `app/features/pipeline.py` never
imports SQLAlchemy or FastAPI: this module knows the *shape* of the work
(the stage sequence, what each stage may raise, how it's logged) but not
how anything is stored. All I/O — writing a log line, resolving "the
dataset", persisting a result, updating the linked experiment — is
delegated to the small async callback hooks `run()` takes, supplied by
`app/services/training.py`, which is the one place a database session
exists. This split is what lets the pipeline itself be unit-tested with
plain async stub functions and no database at all.
"""

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.training.base import ModelAdapter, TrainingDataset, TrainingResult
from app.training.errors import (
    MissingDatasetVersionError,
    ModelInitializationError,
    TrainingExecutionError,
)
from app.training.registry import ModelAdapterRegistry

logger = logging.getLogger("app.training.pipeline")

#: The pipeline's own version, independent of any adapter's `metadata.version`
#: — bump it when the *pipeline* changes in a way that could affect any run's
#: output, mirroring `app.features.pipeline.PIPELINE_VERSION`.
TRAINING_PIPELINE_VERSION = "1.0.0"

#: `(stage_name, level, message)` — the pipeline logs through this hook,
#: never a Python logger, so every stage transition is recorded as a
#: `TrainingJobLog` row a status monitor can poll for.
LogFn = Callable[[str, str, str], Awaitable[None]]
LoadDatasetFn = Callable[[str], Awaitable[TrainingDataset]]
SaveResultsFn = Callable[[TrainingResult], Awaitable[None]]
UpdateExperimentFn = Callable[[TrainingResult], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class TrainingRunOutcome:
    """The result of one successful pipeline run, plus per-stage timing."""

    result: TrainingResult
    stage_durations_ms: dict[str, float]


class TrainingPipeline:
    """Runs a registered model adapter through the fixed six-stage sequence."""

    def __init__(self, registry: ModelAdapterRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> ModelAdapterRegistry:
        """The registry this pipeline resolves model adapters from."""
        return self._registry

    async def run(
        self,
        *,
        model_type: str,
        dataset_version: str | None,
        hyperparameters: Mapping[str, Any],
        log: LogFn,
        load_dataset: LoadDatasetFn,
        save_results: SaveResultsFn,
        update_experiment: UpdateExperimentFn,
    ) -> TrainingRunOutcome:
        """Execute every stage in order, raising on the first failure.

        A caller (the service) is expected to catch any exception, mark the
        job `failed` with the stage the exception carries (via the log
        hook's own stage argument, already recorded before the raise), and
        update the linked experiment itself — this method does not attempt
        any failure-path bookkeeping beyond logging, so a partial run always
        leaves an accurate trail of exactly how far it got.
        """
        durations: dict[str, float] = {}

        async def run_stage(name: str, work: Callable[[], Awaitable[Any]]) -> Any:
            started = perf_counter()
            await log(name, "info", f"Starting stage: {name}")
            try:
                outcome = await work()
            except Exception as exc:
                await log(name, "error", f"Stage failed: {type(exc).__name__}: {exc}")
                raise
            durations[name] = (perf_counter() - started) * 1000
            await log(name, "info", f"Completed stage: {name}")
            return outcome

        async def _validate_dataset() -> ModelAdapter:
            if not dataset_version or not dataset_version.strip():
                raise MissingDatasetVersionError()
            return self._registry.get(model_type)

        adapter = await run_stage("validate_dataset", _validate_dataset)

        assert dataset_version is not None  # narrowed by _validate_dataset above
        dataset = await run_stage("load_dataset", lambda: load_dataset(dataset_version))

        async def _initialize_model() -> None:
            try:
                adapter.initialize(hyperparameters)
            except Exception as exc:  # noqa: BLE001 - deliberate boundary around adapter code
                raise ModelInitializationError(
                    adapter.metadata.name, f"{type(exc).__name__}: {exc}"
                ) from exc

        await run_stage("initialize_model", _initialize_model)

        async def _execute_training() -> TrainingResult:
            try:
                return adapter.train(dataset, hyperparameters)
            except Exception as exc:  # noqa: BLE001 - deliberate boundary around adapter code
                raise TrainingExecutionError(
                    adapter.metadata.name, f"{type(exc).__name__}: {exc}"
                ) from exc

        result = await run_stage("execute_training", _execute_training)

        await run_stage("save_results", lambda: save_results(result))
        await run_stage("update_experiment", lambda: update_experiment(result))

        logger.debug(
            "Training pipeline completed (model_type=%s dataset_version=%s stages=%d)",
            model_type,
            dataset_version,
            len(durations),
        )
        return TrainingRunOutcome(result=result, stage_durations_ms=durations)
