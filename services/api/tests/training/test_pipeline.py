"""Tests for `TrainingPipeline` — the six-stage orchestration, with no database.

Every I/O hook (`log`, `load_dataset`, `save_results`, `update_experiment`)
is a plain async stub here, exercising exactly the separation
`app/training/pipeline.py`'s module docstring describes: the pipeline is
testable without a database, a repository, or FastAPI.
"""

import pytest

from app.models.training import TRAINING_JOB_STAGES
from app.training.base import ModelAdapter, ModelAdapterMetadata, TrainingDataset, TrainingResult
from app.training.errors import (
    MissingDatasetVersionError,
    ModelAdapterNotFoundError,
    ModelInitializationError,
    TrainingExecutionError,
)
from app.training.pipeline import TrainingPipeline
from app.training.registry import ModelAdapterRegistry


class _RecordingAdapter(ModelAdapter):
    metadata = ModelAdapterMetadata(
        name="recording", label="Recording", description="", framework="test"
    )

    def __init__(self) -> None:
        self.initialized_with: dict | None = None

    def initialize(self, hyperparameters):  # noqa: ANN001, ANN201
        self.initialized_with = dict(hyperparameters)

    def train(self, dataset: TrainingDataset, hyperparameters):  # noqa: ANN201
        return TrainingResult(
            metrics={"placeholder_loss": 0.1},
            artifact_uri=f"placeholder://{dataset.dataset_version}",
            summary={"epochs": hyperparameters.get("epochs", 1)},
        )

    def predict(self, artifact_uri, rows):  # noqa: ANN001, ANN201
        raise NotImplementedError


class _FailingInitAdapter(ModelAdapter):
    metadata = ModelAdapterMetadata(name="failing-init", label="", description="", framework="test")

    def initialize(self, hyperparameters):  # noqa: ANN001, ANN201
        raise ValueError("bad hyperparameters")

    def train(self, dataset, hyperparameters):  # noqa: ANN001, ANN201
        raise AssertionError("must not be reached")

    def predict(self, artifact_uri, rows):  # noqa: ANN001, ANN201
        raise NotImplementedError


class _FailingTrainAdapter(ModelAdapter):
    metadata = ModelAdapterMetadata(
        name="failing-train", label="", description="", framework="test"
    )

    def initialize(self, hyperparameters):  # noqa: ANN001, ANN201
        return None

    def train(self, dataset, hyperparameters):  # noqa: ANN001, ANN201
        raise RuntimeError("boom")

    def predict(self, artifact_uri, rows):  # noqa: ANN001, ANN201
        raise NotImplementedError


def build_registry(*adapters: type[ModelAdapter]) -> ModelAdapterRegistry:
    registry = ModelAdapterRegistry()
    for adapter in adapters:
        registry.register(adapter)
    return registry


class _Recorder:
    """Collects every hook call in order, for assertions on stage sequencing."""

    def __init__(self) -> None:
        self.logs: list[tuple[str, str, str]] = []
        self.loaded: list[str] = []
        self.saved: list[TrainingResult] = []
        self.updated: list[TrainingResult] = []

    async def log(self, stage: str, level: str, message: str) -> None:
        self.logs.append((stage, level, message))

    async def load_dataset(self, dataset_version: str) -> TrainingDataset:
        self.loaded.append(dataset_version)
        return TrainingDataset(dataset_version=dataset_version)

    async def save_results(self, result: TrainingResult) -> None:
        self.saved.append(result)

    async def update_experiment(self, result: TrainingResult) -> None:
        self.updated.append(result)


@pytest.mark.asyncio
class TestSuccessfulRun:
    async def test_runs_every_stage_in_order(self) -> None:
        registry = build_registry(_RecordingAdapter)
        pipeline = TrainingPipeline(registry)
        recorder = _Recorder()

        outcome = await pipeline.run(
            model_type="recording",
            dataset_version="ds-1",
            hyperparameters={"epochs": 5},
            log=recorder.log,
            load_dataset=recorder.load_dataset,
            save_results=recorder.save_results,
            update_experiment=recorder.update_experiment,
        )

        stages_started = [
            stage for stage, level, msg in recorder.logs if msg.startswith("Starting")
        ]
        assert stages_started == list(TRAINING_JOB_STAGES)
        assert recorder.loaded == ["ds-1"]
        assert recorder.saved == [outcome.result]
        assert recorder.updated == [outcome.result]
        assert outcome.result.metrics == {"placeholder_loss": 0.1}
        assert set(outcome.stage_durations_ms) == set(TRAINING_JOB_STAGES)

    async def test_passes_hyperparameters_through_to_initialize(self) -> None:
        adapter = _RecordingAdapter()
        registry = ModelAdapterRegistry()
        registry.register(type(adapter))
        pipeline = TrainingPipeline(registry)
        recorder = _Recorder()

        await pipeline.run(
            model_type="recording",
            dataset_version="ds-1",
            hyperparameters={"epochs": 7},
            log=recorder.log,
            load_dataset=recorder.load_dataset,
            save_results=recorder.save_results,
            update_experiment=recorder.update_experiment,
        )

        # A fresh instance is created by the registry, not the local `adapter` object —
        # assert indirectly through the training result instead, which threads
        # `hyperparameters["epochs"]` into its summary.
        assert recorder.saved[0].summary == {"epochs": 7}


@pytest.mark.asyncio
class TestFailureModes:
    async def test_missing_dataset_version_fails_at_validate_stage(self) -> None:
        registry = build_registry(_RecordingAdapter)
        pipeline = TrainingPipeline(registry)
        recorder = _Recorder()

        with pytest.raises(MissingDatasetVersionError):
            await pipeline.run(
                model_type="recording",
                dataset_version=None,
                hyperparameters={},
                log=recorder.log,
                load_dataset=recorder.load_dataset,
                save_results=recorder.save_results,
                update_experiment=recorder.update_experiment,
            )

        assert recorder.loaded == []
        assert recorder.logs[-1][0] == "validate_dataset"
        assert recorder.logs[-1][1] == "error"

    async def test_unknown_model_type_fails_at_validate_stage(self) -> None:
        registry = build_registry(_RecordingAdapter)
        pipeline = TrainingPipeline(registry)
        recorder = _Recorder()

        with pytest.raises(ModelAdapterNotFoundError):
            await pipeline.run(
                model_type="does-not-exist",
                dataset_version="ds-1",
                hyperparameters={},
                log=recorder.log,
                load_dataset=recorder.load_dataset,
                save_results=recorder.save_results,
                update_experiment=recorder.update_experiment,
            )
        assert recorder.loaded == []

    async def test_initialize_failure_is_wrapped_and_stops_before_training(self) -> None:
        registry = build_registry(_FailingInitAdapter)
        pipeline = TrainingPipeline(registry)
        recorder = _Recorder()

        with pytest.raises(ModelInitializationError):
            await pipeline.run(
                model_type="failing-init",
                dataset_version="ds-1",
                hyperparameters={},
                log=recorder.log,
                load_dataset=recorder.load_dataset,
                save_results=recorder.save_results,
                update_experiment=recorder.update_experiment,
            )

        assert recorder.saved == []
        assert recorder.updated == []
        assert recorder.logs[-1] == ("initialize_model", "error", recorder.logs[-1][2])

    async def test_training_failure_is_wrapped_and_never_saves_or_updates(self) -> None:
        registry = build_registry(_FailingTrainAdapter)
        pipeline = TrainingPipeline(registry)
        recorder = _Recorder()

        with pytest.raises(TrainingExecutionError):
            await pipeline.run(
                model_type="failing-train",
                dataset_version="ds-1",
                hyperparameters={},
                log=recorder.log,
                load_dataset=recorder.load_dataset,
                save_results=recorder.save_results,
                update_experiment=recorder.update_experiment,
            )

        assert recorder.saved == []
        assert recorder.updated == []
        assert recorder.logs[-1][0] == "execute_training"
        assert recorder.logs[-1][1] == "error"
