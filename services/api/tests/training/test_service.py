"""Tests for `TrainingJobService` — lifecycle, pipeline execution, and experiment integration."""

import uuid

import pytest

from app.repositories.experiments import ExperimentRepository
from app.repositories.training import TrainingJobRepository
from app.schemas.experiments import ExperimentCreateRequest
from app.schemas.training import TrainingJobCreateRequest
from app.services.experiments import ExperimentService
from app.services.training import TrainingJobService
from app.training.adapters import load_builtin_model_adapters
from app.training.errors import (
    InvalidTrainingJobSortError,
    TrainingJobNotCancellableError,
    TrainingJobNotFoundError,
)
from app.training.pipeline import TrainingPipeline
from app.training.registry import default_registry
from tests.conftest import SessionFactory


def build_service(session_factory: SessionFactory) -> TrainingJobService:
    load_builtin_model_adapters()
    session = session_factory()
    return TrainingJobService(
        repository=TrainingJobRepository(session),
        experiment_service=ExperimentService(repository=ExperimentRepository(session)),
        pipeline=TrainingPipeline(default_registry),
    )


async def seed_experiment(session_factory: SessionFactory, **overrides: object) -> str:
    service = ExperimentService(repository=ExperimentRepository(session_factory()))
    payload = {"name": "training target experiment"}
    payload.update(overrides)
    experiment = await service.create(ExperimentCreateRequest(**payload))
    return experiment.id


@pytest.mark.asyncio
class TestCreate:
    async def test_creates_a_pending_job(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-abc")
        service = build_service(session_factory)

        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        assert job.status == "pending"
        assert job.model_type == "placeholder"
        assert job.dataset_version == "ds-abc"
        assert job.logs == []

    async def test_dataset_version_override_takes_precedence(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-abc")
        service = build_service(session_factory)

        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id, model_type="placeholder", dataset_version="ds-override"
            )
        )

        assert job.dataset_version == "ds-override"

    async def test_raises_experiment_not_found_for_an_unknown_experiment(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        from app.services.experiments import ExperimentNotFoundError

        with pytest.raises(ExperimentNotFoundError):
            await service.create(
                TrainingJobCreateRequest(experiment_id=uuid.uuid4(), model_type="placeholder")
            )


@pytest.mark.asyncio
class TestGetAndSearch:
    async def test_get_returns_an_existing_job(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)
        service = build_service(session_factory)
        created = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        fetched = await service.get(uuid.UUID(created.id))

        assert fetched.id == created.id
        assert fetched.model_type == "placeholder"

    async def test_get_raises_not_found_for_an_unknown_id(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(TrainingJobNotFoundError):
            await service.get(uuid.uuid4())

    async def test_search_filters_by_experiment(self, session_factory: SessionFactory) -> None:
        exp_a = await seed_experiment(session_factory, name="a")
        exp_b = await seed_experiment(session_factory, name="b")
        service = build_service(session_factory)
        await service.create(
            TrainingJobCreateRequest(experiment_id=exp_a, model_type="placeholder")
        )
        await service.create(
            TrainingJobCreateRequest(experiment_id=exp_b, model_type="placeholder")
        )

        result = await service.search(
            experiment_id=uuid.UUID(exp_a),
            status_filter=None,
            model_type=None,
            sort="created_at",
            direction="asc",
            limit=10,
            offset=0,
        )

        assert result.total == 1
        assert result.jobs[0].experiment_id == exp_a

    async def test_search_rejects_an_invalid_sort_column(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(InvalidTrainingJobSortError):
            await service.search(
                experiment_id=None,
                status_filter=None,
                model_type=None,
                sort="not_a_column",
                direction="asc",
                limit=10,
                offset=0,
            )


@pytest.mark.asyncio
class TestDelete:
    async def test_deletes_a_pending_job(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        await service.delete(uuid.UUID(job.id))

        with pytest.raises(TrainingJobNotFoundError):
            await service.get(uuid.UUID(job.id))

    async def test_refuses_to_delete_a_running_job(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-1")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        repo = TrainingJobRepository(session_factory())
        running_job = await repo.get_by_id(uuid.UUID(job.id))
        assert running_job is not None
        await repo.update(running_job, {"status": "running"})

        with pytest.raises(TrainingJobNotCancellableError):
            await service.delete(uuid.UUID(job.id))


@pytest.mark.asyncio
class TestCancel:
    async def test_cancels_a_pending_job(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        cancelled = await service.cancel(uuid.UUID(job.id))

        assert cancelled.status == "cancelled"
        assert cancelled.completed_at is not None


@pytest.mark.asyncio
class TestRun:
    async def test_completes_and_updates_the_linked_experiment(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-run")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="placeholder",
                hyperparameters={"epochs": 3},
            )
        )

        completed = await service.run(uuid.UUID(job.id))

        assert completed.status == "completed"
        assert completed.current_stage == "update_experiment"
        assert completed.started_at is not None
        assert completed.completed_at is not None
        assert completed.result_summary is not None
        assert "placeholder_loss" in completed.result_summary["metrics"]
        assert any(log.stage == "execute_training" for log in completed.logs)

        experiment = await ExperimentService(
            repository=ExperimentRepository(session_factory())
        ).get(uuid.UUID(experiment_id))
        assert experiment.status == "completed"
        assert any(m.name == "placeholder_loss" for m in experiment.metrics)
        assert any(a.artifact_type == "model_checkpoint" for a in experiment.artifacts)

    async def test_fails_when_experiment_has_no_dataset_version(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)  # no dataset_version
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        failed = await service.run(uuid.UUID(job.id))

        assert failed.status == "failed"
        assert failed.error_message is not None
        assert "dataset_version" in failed.error_message

        experiment = await ExperimentService(
            repository=ExperimentRepository(session_factory())
        ).get(uuid.UUID(experiment_id))
        assert experiment.status == "failed"

    async def test_fails_for_an_unknown_model_adapter(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-1")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="does-not-exist")
        )

        failed = await service.run(uuid.UUID(job.id))

        assert failed.status == "failed"

    async def test_run_failure_is_resilient_to_the_experiment_already_being_gone(
        self, session_factory: SessionFactory
    ) -> None:
        """A best-effort `_mark_experiment_failed` must not blow up `run()` itself."""
        experiment_id = await seed_experiment(session_factory)  # no dataset_version -> fails
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        exp_repo = ExperimentRepository(session_factory())
        experiment = await exp_repo.get_by_id(uuid.UUID(experiment_id))
        assert experiment is not None
        await exp_repo.delete(experiment)

        failed = await service.run(uuid.UUID(job.id))

        assert failed.status == "failed"

    async def test_cannot_run_a_job_twice(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-1")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        await service.run(uuid.UUID(job.id))

        from app.training.errors import InvalidTrainingJobTransitionError

        with pytest.raises(InvalidTrainingJobTransitionError):
            await service.run(uuid.UUID(job.id))


class TestListModelAdapters:
    def test_lists_the_placeholder_adapter(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        catalog = service.list_model_adapters()
        names = [a.name for a in catalog.adapters]
        assert "placeholder" in names
