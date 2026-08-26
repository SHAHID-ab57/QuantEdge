"""PostgreSQL-backed training job repository tests (opt-in profile).

Marked ``postgres``, mirroring `test_candles_postgres.py` exactly: the
fixture reads ``TEST_DATABASE_URL`` and auto-skips when the database is
unreachable. This is the one place `ON DELETE CASCADE` (declared on
`training_jobs.experiment_id` and `training_job_logs.job_id`, applied in
Alembic revision ``8cc1992f6c6f``) is actually exercised — the default
in-memory SQLite suite does not enable ``PRAGMA foreign_keys``, so it
cannot verify real cascade-on-delete behavior.
"""

from uuid import UUID

import pytest

from app.models import Experiment
from app.models.training import TrainingJob, TrainingJobLog
from app.repositories.experiments import ExperimentRepository
from app.repositories.training import TrainingJobRepository

pytestmark = pytest.mark.postgres


async def seed_experiment_with_job(pg_session_factory) -> tuple[UUID, UUID]:
    async with pg_session_factory() as session:
        experiment = await ExperimentRepository(session).create(Experiment(name="pg cascade test"))
        job = await TrainingJobRepository(session).create(
            TrainingJob(experiment_id=experiment.id, model_type="placeholder")
        )
        return experiment.id, job.id


async def test_deleting_the_experiment_cascades_to_its_training_jobs(pg_session_factory) -> None:
    experiment_id, job_id = await seed_experiment_with_job(pg_session_factory)

    async with pg_session_factory() as session:
        exp_repo = ExperimentRepository(session)
        experiment = await exp_repo.get_by_id(experiment_id)
        assert experiment is not None
        await exp_repo.delete(experiment)

    async with pg_session_factory() as session:
        assert await TrainingJobRepository(session).get_by_id(job_id) is None


async def test_deleting_the_job_cascades_to_its_logs(pg_session_factory) -> None:
    experiment_id, job_id = await seed_experiment_with_job(pg_session_factory)

    async with pg_session_factory() as session:
        job_repo = TrainingJobRepository(session)
        await job_repo.add_log(TrainingJobLog(job_id=job_id, level="info", message="hello"))
        job = await job_repo.get_by_id(job_id)
        assert job is not None
        assert len(job.logs) == 1
        await job_repo.delete(job)

    async with pg_session_factory() as session:
        result = await session.get(TrainingJobLog, job.logs[0].id)
        assert result is None
