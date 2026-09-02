"""Tests for the non-blocking `/training-jobs/{id}/run` background execution seam
(`app/dependencies/training.py`): its own DB session, failure handling (both the
pipeline's own and a crash outside it), and shutdown/test wait helpers.

Mirrors `tests/services/test_candle_sync.py`'s own convention for testing a
`get_engine()`-backed background component: monkeypatch `get_engine` to the
test's in-memory engine, since this code intentionally never goes through
`get_db`/FastAPI's dependency overrides (see the module's own docstring for why).
"""

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

import app.dependencies.training as training_dependencies
from app.dependencies.training import (
    cancel_in_flight_training_jobs,
    run_training_job_in_background,
    schedule_training_job,
    wait_for_in_flight_training_jobs,
)
from app.repositories.experiments import ExperimentRepository
from app.repositories.training import TrainingJobRepository
from app.schemas.training import TrainingJobCreateRequest
from app.services.experiments import ExperimentService
from app.services.training import TrainingJobService
from app.training.pipeline import TrainingPipeline
from app.training.registry import default_registry
from tests.conftest import SessionFactory
from tests.ml_datasets.test_service import build_service as build_ml_dataset_service
from tests.training.test_service import build_service, seed_experiment


@pytest.fixture(autouse=True)
def _background_uses_the_test_engine(monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine) -> None:
    """Every test in this file points the module's `get_engine()` at the
    shared in-memory test engine, so a background task opens a session
    against the same database `session_factory` does."""
    monkeypatch.setattr(training_dependencies, "get_engine", lambda: engine)


async def fetch_status(session_factory: SessionFactory, job_id: uuid.UUID) -> str:
    async with session_factory() as session:
        job = await TrainingJobRepository(session).get_by_id(job_id)
        assert job is not None
        return job.status


class TestOwnDatabaseSession:
    async def test_background_task_reads_and_writes_after_the_original_session_closed(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-bg")
        starter_session = session_factory()
        starter = TrainingJobService(
            repository=TrainingJobRepository(starter_session),
            experiment_service=ExperimentService(repository=ExperimentRepository(starter_session)),
            pipeline=TrainingPipeline(default_registry),
            ml_dataset_service=build_ml_dataset_service(session_factory),
        )
        job = await starter.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id, model_type="placeholder", hyperparameters={"epochs": 2}
            )
        )
        await starter.start(uuid.UUID(job.id))
        # Simulate the request ending: the session `get_db` would have closed
        # by the time a background task actually runs is closed here too.
        await starter_session.close()

        await run_training_job_in_background(uuid.UUID(job.id))

        status = await fetch_status(session_factory, uuid.UUID(job.id))
        assert status == "completed"

    async def test_no_engine_configured_returns_without_raising(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(training_dependencies, "get_engine", lambda: None)
        # Never raises even though no session can be opened — logged and returned.
        await run_training_job_in_background(uuid.uuid4())


class TestFailurePaths:
    async def test_a_pipeline_failure_marks_the_job_failed(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)  # no dataset_version -> fails
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        await service.start(uuid.UUID(job.id))

        await run_training_job_in_background(uuid.UUID(job.id))

        async with session_factory() as session:
            failed = await TrainingJobRepository(session).get_by_id(uuid.UUID(job.id))
        assert failed is not None
        assert failed.status == "failed"
        assert failed.error_message is not None

    async def test_a_crash_outside_execute_run_is_still_marked_failed(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`execute_run` itself raising (rather than catching its own pipeline
        error, already covered above) exercises `run_training_job_in_background`'s
        own outer `except Exception` — a background task's crash must not just
        vanish; it still marks the job failed via `_mark_job_failed_after_crash`."""
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-crash")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        await service.start(uuid.UUID(job.id))

        async def boom(self: TrainingJobService, job_id: uuid.UUID):
            raise RuntimeError("simulated crash outside the pipeline's own try/except")

        monkeypatch.setattr(TrainingJobService, "execute_run", boom)

        await run_training_job_in_background(uuid.UUID(job.id))

        status = await fetch_status(session_factory, uuid.UUID(job.id))
        assert status == "failed"

    async def test_a_failure_in_the_crash_recovery_write_itself_leaves_the_job_running(
        self, session_factory: SessionFactory, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`_mark_job_failed_after_crash` is itself only best-effort — this
        proves what actually happens when *it* also can't open a session
        (e.g. the same outage that caused the original crash), rather than
        just asserting it in prose. `get_engine()` is made to succeed for
        `run_training_job_in_background`'s own main session (call #1, so
        the crash in `execute_run` happens exactly as in the test above)
        and fail for `_mark_job_failed_after_crash`'s separate call (#2).

        The result is not a silent success: the job is left exactly as
        `start` set it — `'running'`, never touched by the failed recovery
        write — matching the disclosed 'no alerting' limitation in
        `ARCHITECTURE.md` § "Machine Learning Training Framework". The
        background task itself still must not raise: a doubly-failed
        crash-and-recovery is not a second unhandled exception.
        """
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-crash-recovery")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        await service.start(uuid.UUID(job.id))

        async def boom(self: TrainingJobService, job_id: uuid.UUID):
            raise RuntimeError("simulated crash outside the pipeline's own try/except")

        monkeypatch.setattr(TrainingJobService, "execute_run", boom)

        calls = {"n": 0}

        def flaky_get_engine():
            calls["n"] += 1
            if calls["n"] == 1:
                return engine  # run_training_job_in_background's own main session
            raise RuntimeError("simulated: database unreachable for the recovery write too")

        monkeypatch.setattr(training_dependencies, "get_engine", flaky_get_engine)

        await run_training_job_in_background(uuid.UUID(job.id))  # must not raise

        assert calls["n"] == 2  # both the main session and the recovery attempt were tried
        status = await fetch_status(session_factory, uuid.UUID(job.id))
        assert (
            status == "running"
        )  # left exactly where the crash found it — not silently anything else


class TestSchedulingAndWaiting:
    async def test_wait_for_in_flight_training_jobs_deterministically_awaits_completion(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-wait")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        await service.start(uuid.UUID(job.id))

        schedule_training_job(uuid.UUID(job.id))
        # No sleep of any kind — this is the deterministic wait itself.
        await wait_for_in_flight_training_jobs()

        status = await fetch_status(session_factory, uuid.UUID(job.id))
        assert status == "completed"

    async def test_cancel_in_flight_training_jobs_cancels_and_untracks_a_hanging_task(
        self,
    ) -> None:
        """Mirrors `CandleSyncScheduler.stop()`'s cancel-then-await pattern,
        applied to a dynamic set of per-request tasks — exercised directly
        against `_track`/`_background_tasks` (bypassing a real DB session,
        which a cancelled-mid-transaction in-memory SQLite test connection
        does not reliably survive) rather than through
        `schedule_training_job`. `execute_run`'s own DB-session behavior is
        already covered by the other tests in this class; what's specific
        to shutdown is that a still-running task actually gets cancelled
        and stops being tracked — proven here.

        `asyncio.CancelledError` is not an `Exception` subclass, so
        `run_training_job_in_background`'s own `except Exception` (and, in
        a real run, `execute_run`'s) never sees it — a cancelled task never
        gets the chance to mark its job 'failed' the normal way, which is
        exactly the disclosed limitation `cancel_in_flight_training_jobs`'s
        own docstring describes: a job whose task was cancelled at shutdown
        is left 'running' in the database, not cleanly failed.
        """
        started = asyncio.Event()

        async def hang_forever() -> None:
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(hang_forever())
        training_dependencies._track(task)  # noqa: SLF001 - white-box: exercising the tracker directly
        await started.wait()

        await cancel_in_flight_training_jobs()

        assert task.cancelled()
        assert len(training_dependencies._background_tasks) == 0  # noqa: SLF001
