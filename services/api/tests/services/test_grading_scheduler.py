"""Tests for the periodic prediction grading scheduler.

Mirrors `tests/services/test_candle_sync.py`'s own conventions exactly:
`get_engine` monkeypatched to the test's in-memory engine (this scheduler
never goes through `get_db`/FastAPI's dependency overrides, the same
reason `CandleSyncScheduler` doesn't), a real seeded prediction rather than
a faked grading path (grading logic itself is already covered by
`tests/prediction/test_grading.py`/`test_service.py` — these tests focus on
the scheduler's own start/stop/loop/tick wiring).
"""

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.schemas.prediction import PredictionRunRequest
from app.services import grading_scheduler
from app.services.grading_scheduler import PredictionGradingScheduler, run_grading_once
from tests.conftest import SessionFactory
from tests.prediction.test_service import (
    EARLY_AS_OF_FOR_GRADING,
    build_prediction_service,
    train_completed_job,
)


@pytest.fixture(autouse=True)
def _use_test_engine(monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine) -> None:
    monkeypatch.setattr(grading_scheduler, "get_engine", lambda: engine)


class TestStartStop:
    async def test_start_noops_without_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without a database the scheduler does not create a loop task."""
        monkeypatch.setattr(grading_scheduler, "get_engine", lambda: None)
        scheduler = PredictionGradingScheduler()
        await scheduler.start()
        assert not scheduler.running
        await scheduler.stop()

    async def test_stop_without_start_is_a_noop(self) -> None:
        scheduler = PredictionGradingScheduler()
        await scheduler.stop()
        assert not scheduler.running

    async def test_starting_twice_does_not_create_a_second_task(self) -> None:
        scheduler = PredictionGradingScheduler(interval_seconds=60)
        await scheduler.start()
        first_task = scheduler._task  # noqa: SLF001 - white-box: proving no second task
        await scheduler.start()
        assert scheduler._task is first_task  # noqa: SLF001
        await scheduler.stop()


class TestRunGradingTick:
    async def test_tick_grades_a_ready_prediction(self, session_factory: SessionFactory) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="SCHEDGRADEUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        prediction = await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="SCHEDGRADEUSD",
                as_of=EARLY_AS_OF_FOR_GRADING,
            )
        )
        assert prediction.actual_outcome is None

        scheduler = PredictionGradingScheduler()
        summary = await scheduler.run_grading_tick()

        assert summary.attempted == 1
        assert summary.graded == 1
        assert summary.not_yet_knowable == 0
        assert summary.failed == 0
        assert summary.duration_seconds >= 0.0

        graded = await service.get(uuid.UUID(prediction.id))
        assert graded.actual_outcome is not None

    async def test_tick_without_an_engine_reports_an_empty_summary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(grading_scheduler, "get_engine", lambda: None)
        scheduler = PredictionGradingScheduler()
        summary = await scheduler.run_grading_tick()
        assert summary.attempted == 0
        assert summary.graded == 0


class TestRunGradingOnce:
    async def test_run_grading_once_runs_a_single_tick(
        self, session_factory: SessionFactory
    ) -> None:
        job_id, _ = await train_completed_job(
            session_factory, symbol="ONCEGRADEUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        prediction = await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="ONCEGRADEUSD",
                as_of=EARLY_AS_OF_FOR_GRADING,
            )
        )

        summary = await run_grading_once()

        assert summary.graded == 1
        graded = await service.get(uuid.UUID(prediction.id))
        assert graded.actual_outcome is not None


class TestLoop:
    async def test_loop_runs_a_tick_then_stops_cleanly(
        self, session_factory: SessionFactory
    ) -> None:
        """The background loop starts, runs at least one tick, and stops."""
        job_id, _ = await train_completed_job(
            session_factory, symbol="LOOPGRADEUSD", model_type="logistic_regression"
        )
        service = build_prediction_service(session_factory)
        prediction = await service.run(
            PredictionRunRequest(
                training_job_id=uuid.UUID(job_id),
                symbol="LOOPGRADEUSD",
                as_of=EARLY_AS_OF_FOR_GRADING,
            )
        )

        scheduler = PredictionGradingScheduler(interval_seconds=60)
        await scheduler.start()
        assert scheduler.running

        for _ in range(50):
            graded = await service.get(uuid.UUID(prediction.id))
            if graded.actual_outcome is not None:
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("first tick never graded the prediction")

        await scheduler.stop()
        assert not scheduler.running
