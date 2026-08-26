"""Tests for `TrainingJobRepository` — CRUD, search, filter, sort, and logs."""

import uuid

import pytest

from app.models.experiment import Experiment
from app.models.training import TrainingJob, TrainingJobLog
from app.repositories.experiments import ExperimentRepository
from app.repositories.training import TrainingJobFilters, TrainingJobRepository
from tests.conftest import SessionFactory


async def seed_experiment(session_factory: SessionFactory, *, name: str = "exp") -> uuid.UUID:
    async with session_factory() as session:
        created = await ExperimentRepository(session).create(Experiment(name=name))
        return created.id


async def seed_job(
    session_factory: SessionFactory,
    *,
    experiment_id: uuid.UUID,
    model_type: str = "placeholder",
    status: str = "pending",
    dataset_version: str | None = "ds-1",
) -> uuid.UUID:
    async with session_factory() as session:
        created = await TrainingJobRepository(session).create(
            TrainingJob(
                experiment_id=experiment_id,
                model_type=model_type,
                status=status,
                dataset_version=dataset_version,
            )
        )
        return created.id


@pytest.mark.asyncio
class TestCreateAndGet:
    async def test_creates_and_retrieves_a_job(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)

        async with session_factory() as session:
            created = await TrainingJobRepository(session).create(
                TrainingJob(experiment_id=experiment_id, model_type="placeholder")
            )

        async with session_factory() as session:
            found = await TrainingJobRepository(session).get_by_id(created.id)

        assert found is not None
        assert found.experiment_id == experiment_id
        assert found.model_type == "placeholder"
        assert found.status == "pending"
        assert found.logs == []

    async def test_returns_none_for_an_unknown_id(self, session_factory: SessionFactory) -> None:
        async with session_factory() as session:
            found = await TrainingJobRepository(session).get_by_id(uuid.uuid4())
        assert found is None

    async def test_persists_hyperparameters_json(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)
        async with session_factory() as session:
            created = await TrainingJobRepository(session).create(
                TrainingJob(
                    experiment_id=experiment_id,
                    model_type="placeholder",
                    hyperparameters={"epochs": 5, "learning_rate": 0.01},
                )
            )

        async with session_factory() as session:
            found = await TrainingJobRepository(session).get_by_id(created.id)

        assert found is not None
        assert found.hyperparameters == {"epochs": 5, "learning_rate": 0.01}


@pytest.mark.asyncio
class TestUpdateAndDelete:
    async def test_update_applies_only_given_fields(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)
        job_id = await seed_job(session_factory, experiment_id=experiment_id)

        async with session_factory() as session:
            repo = TrainingJobRepository(session)
            job = await repo.get_by_id(job_id)
            assert job is not None
            updated = await repo.update(job, {"status": "running", "current_stage": "load_dataset"})

        assert updated.status == "running"
        assert updated.current_stage == "load_dataset"
        assert updated.model_type == "placeholder"

    async def test_delete_removes_the_job_and_its_logs(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        job_id = await seed_job(session_factory, experiment_id=experiment_id)

        async with session_factory() as session:
            repo = TrainingJobRepository(session)
            await repo.add_log(TrainingJobLog(job_id=job_id, level="info", message="hello"))

        async with session_factory() as session:
            repo = TrainingJobRepository(session)
            job = await repo.get_by_id(job_id)
            assert job is not None
            await repo.delete(job)

        async with session_factory() as session:
            assert await TrainingJobRepository(session).get_by_id(job_id) is None

    # Deleting the linked experiment cascading to its training jobs relies on the
    # database's own `ON DELETE CASCADE` (verified applied in the Alembic migration
    # and exercised for real in `tests/repository/test_training_postgres.py`) rather
    # than an ORM-level relationship cascade — the in-memory SQLite test engine does
    # not enable `PRAGMA foreign_keys`, so it cannot exercise this path meaningfully.


@pytest.mark.asyncio
class TestLogs:
    async def test_add_log_appends_and_is_returned_in_order(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        job_id = await seed_job(session_factory, experiment_id=experiment_id)

        async with session_factory() as session:
            repo = TrainingJobRepository(session)
            await repo.add_log(TrainingJobLog(job_id=job_id, level="info", message="first"))
            await repo.add_log(TrainingJobLog(job_id=job_id, level="error", message="second"))

        async with session_factory() as session:
            job = await TrainingJobRepository(session).get_by_id(job_id)

        assert job is not None
        assert [log.message for log in job.logs] == ["first", "second"]


@pytest.mark.asyncio
class TestSearchFilterSort:
    async def test_filters_by_experiment_id(self, session_factory: SessionFactory) -> None:
        exp_a = await seed_experiment(session_factory, name="a")
        exp_b = await seed_experiment(session_factory, name="b")
        await seed_job(session_factory, experiment_id=exp_a)
        await seed_job(session_factory, experiment_id=exp_b)

        async with session_factory() as session:
            results, total = await TrainingJobRepository(session).search(
                TrainingJobFilters(experiment_id=exp_a),
                sort="created_at",
                direction="asc",
                limit=10,
                offset=0,
            )

        assert total == 1
        assert results[0].experiment_id == exp_a

    async def test_filters_by_status(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)
        await seed_job(session_factory, experiment_id=experiment_id, status="pending")
        await seed_job(session_factory, experiment_id=experiment_id, status="completed")

        async with session_factory() as session:
            results, total = await TrainingJobRepository(session).search(
                TrainingJobFilters(status="completed"),
                sort="created_at",
                direction="asc",
                limit=10,
                offset=0,
            )

        assert total == 1
        assert results[0].status == "completed"

    async def test_filters_by_model_type(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)
        await seed_job(session_factory, experiment_id=experiment_id, model_type="placeholder")
        await seed_job(session_factory, experiment_id=experiment_id, model_type="other")

        async with session_factory() as session:
            results, total = await TrainingJobRepository(session).search(
                TrainingJobFilters(model_type="other"),
                sort="created_at",
                direction="asc",
                limit=10,
                offset=0,
            )

        assert total == 1
        assert results[0].model_type == "other"

    async def test_sorts_by_status_ascending(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)
        await seed_job(session_factory, experiment_id=experiment_id, status="running")
        await seed_job(session_factory, experiment_id=experiment_id, status="completed")
        await seed_job(session_factory, experiment_id=experiment_id, status="pending")

        async with session_factory() as session:
            results, _ = await TrainingJobRepository(session).search(
                TrainingJobFilters(), sort="status", direction="asc", limit=10, offset=0
            )

        assert [r.status for r in results] == ["completed", "pending", "running"]

    async def test_paginates_with_limit_and_offset(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)
        for _ in range(4):
            await seed_job(session_factory, experiment_id=experiment_id)

        async with session_factory() as session:
            page, total = await TrainingJobRepository(session).search(
                TrainingJobFilters(), sort="created_at", direction="asc", limit=2, offset=1
            )

        assert total == 4
        assert len(page) == 2
