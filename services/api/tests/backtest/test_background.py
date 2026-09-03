"""Tests for the non-blocking `POST /backtests/run` background execution seam
(`app/dependencies/backtest.py`): its own DB session, failure handling (both
`execute_run`'s own and a crash outside it), and shutdown/test wait helpers.

Mirrors `tests/training/test_background.py`'s own convention exactly — the
same shared `app.services.background_tasks` registry backs both, so most of
this suite proves the identical guarantees training already has, now hold
for a backtest run too.
"""

import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

import app.dependencies.backtest as backtest_dependencies
from app.dependencies.backtest import (
    run_backtest_in_background,
    schedule_backtest_run,
)
from app.repositories.backtest_runs import BacktestRunRepository
from app.schemas.backtest import BacktestRunRequest
from app.services import background_tasks
from app.services.backtest import BacktestService
from tests.backtest.test_service import BASE, build_backtest_service
from tests.conftest import SessionFactory
from tests.prediction.test_service import train_completed_job


@pytest.fixture(autouse=True)
def _backtest_background_uses_the_test_engine(
    monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine
) -> None:
    """Every test in this file points the module's `get_engine()` at the
    shared in-memory test engine, so a background task opens a session
    against the same database `session_factory` does."""
    monkeypatch.setattr(backtest_dependencies, "get_engine", lambda: engine)


async def fetch_status(session_factory: SessionFactory, run_id: uuid.UUID) -> str:
    async with session_factory() as session:
        run = await BacktestRunRepository(session).get_by_id(run_id)
        assert run is not None
        return run.status


class TestOwnDatabaseSession:
    async def test_background_task_reads_and_writes_after_the_original_session_closed(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTBGUSD", model_type="logistic_regression"
        )
        starter = build_backtest_service(session_factory)
        run = await starter.start(
            BacktestRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="BTBGUSD",
                start=BASE + timedelta(hours=40),
                end=BASE + timedelta(hours=42),
            )
        )
        assert run.status == "running"

        await run_backtest_in_background(uuid.UUID(run.id))

        status = await fetch_status(session_factory, uuid.UUID(run.id))
        assert status == "completed"

    async def test_no_engine_configured_returns_without_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(backtest_dependencies, "get_engine", lambda: None)
        # Never raises even though no session can be opened — logged and returned.
        await run_backtest_in_background(uuid.uuid4())


class TestFailurePaths:
    async def test_a_crash_outside_execute_run_is_still_marked_failed(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`execute_run` itself raising (rather than converting its own
        internal failure into a 'failed' row, already covered elsewhere)
        exercises `run_backtest_in_background`'s own outer `except
        Exception` — a background task's crash must not just vanish."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTCRASHUSD", model_type="logistic_regression"
        )
        starter = build_backtest_service(session_factory)
        run = await starter.start(
            BacktestRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="BTCRASHUSD",
                start=BASE + timedelta(hours=40),
                end=BASE + timedelta(hours=42),
            )
        )

        async def boom(self: BacktestService, run_id: uuid.UUID):
            raise RuntimeError("simulated crash outside execute_run's own try/except")

        monkeypatch.setattr(BacktestService, "execute_run", boom)

        await run_backtest_in_background(uuid.UUID(run.id))

        status = await fetch_status(session_factory, uuid.UUID(run.id))
        assert status == "failed"

    async def test_a_failure_in_the_crash_recovery_write_itself_leaves_the_run_running(
        self, session_factory: SessionFactory, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mirrors `test_background.py`'s identical training-job test:
        `_mark_run_failed_after_crash` is itself only best-effort. Left
        exactly as `start` set it — `'running'` — never touched by the
        failed recovery write, and the background task itself still must
        not raise."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTCRASHRECUSD", model_type="logistic_regression"
        )
        starter = build_backtest_service(session_factory)
        run = await starter.start(
            BacktestRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="BTCRASHRECUSD",
                start=BASE + timedelta(hours=40),
                end=BASE + timedelta(hours=42),
            )
        )

        async def boom(self: BacktestService, run_id: uuid.UUID):
            raise RuntimeError("simulated crash outside execute_run's own try/except")

        monkeypatch.setattr(BacktestService, "execute_run", boom)

        calls = {"n": 0}

        def flaky_get_engine():
            calls["n"] += 1
            if calls["n"] == 1:
                return engine  # run_backtest_in_background's own main session
            raise RuntimeError("simulated: database unreachable for the recovery write too")

        monkeypatch.setattr(backtest_dependencies, "get_engine", flaky_get_engine)

        await run_backtest_in_background(uuid.UUID(run.id))  # must not raise

        assert calls["n"] == 2
        status = await fetch_status(session_factory, uuid.UUID(run.id))
        assert status == "running"


class TestSchedulingAndWaiting:
    async def test_wait_for_all_deterministically_awaits_a_scheduled_backtest(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="BTWAITUSD", model_type="logistic_regression"
        )
        starter = build_backtest_service(session_factory)
        run = await starter.start(
            BacktestRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="BTWAITUSD",
                start=BASE + timedelta(hours=40),
                end=BASE + timedelta(hours=42),
            )
        )

        schedule_backtest_run(uuid.UUID(run.id))
        # No sleep of any kind — this is the deterministic wait itself, and
        # the exact same shared registry `wait_for_in_flight_training_jobs`
        # delegates to — not a second mechanism.
        await background_tasks.wait_for_all()

        status = await fetch_status(session_factory, uuid.UUID(run.id))
        assert status == "completed"

    async def test_cancel_all_cancels_and_untracks_a_hanging_backtest_task(self) -> None:
        """Mirrors `test_background.py`'s identical training-job test: the
        shared registry's cancel-then-await, exercised directly against
        `track`/`_tasks` (bypassing a real DB session) rather than through
        `schedule_backtest_run` — what's specific to shutdown is that a
        still-running task actually gets cancelled and stops being tracked,
        proven here for the exact same registry a real backtest task uses.
        """
        started = asyncio.Event()

        async def hang_forever() -> None:
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(hang_forever())
        background_tasks.track(task)
        await started.wait()

        await background_tasks.cancel_all()

        assert task.cancelled()
        assert len(background_tasks._tasks) == 0  # noqa: SLF001 - white-box check
