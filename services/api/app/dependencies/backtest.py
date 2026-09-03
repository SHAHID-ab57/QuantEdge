"""Dependency providers for the Backtesting Engine API.

Also owns the background-execution seam `POST /backtests/run` uses so the
request returns before the walk completes — mirrors
`app/dependencies/training.py` exactly: a background task opens its own DB
session bound to the process-wide engine (`get_engine()`), never the
request's own (which is closed by the time the task actually runs), and is
tracked via the *same* shared `app.services.background_tasks` registry
`schedule_training_job` already uses — not a second mechanism (see that
module's own docstring for why it was extracted).
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db.engine import get_engine
from app.db.session import get_db
from app.dependencies.prediction import get_prediction_service
from app.dependencies.training import get_training_job_service
from app.repositories.backtest_runs import BacktestRunRepository
from app.services import background_tasks
from app.services.backtest import BacktestService

logger = logging.getLogger("app.dependencies.backtest")


def get_backtest_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BacktestService:
    """Build the backtest service wired to the request session.

    Composes `PredictionService`/`TrainingJobService` directly (never a
    second copy of either) via their own existing dependency providers —
    the exact same instances a live `POST /predictions/run` or
    `POST /training-jobs/{id}/run` call would get for this request.
    """
    return BacktestService(
        repository=BacktestRunRepository(session),
        prediction_service=get_prediction_service(session),
        training_job_service=get_training_job_service(session),
        max_steps=get_settings().max_backtest_steps,
    )


async def run_backtest_in_background(run_id: uuid.UUID) -> None:
    """Run `BacktestService.execute_run` for `run_id` in a background task.

    Mirrors `app.dependencies.training.run_training_job_in_background`
    exactly — see that function's own docstring for the full reasoning (a
    fresh session bound to `get_engine()`, never the request's own; an outer
    `except Exception` net for anything `execute_run` itself doesn't already
    convert into a 'failed' row; a deliberate non-catch of
    `asyncio.CancelledError` so a cancelled-at-shutdown run is left exactly
    where it was, not reinterpreted as a normal failure).
    """
    engine = get_engine()
    if engine is None:
        logger.error(
            "Cannot execute backtest run %s in background: database is not configured",
            run_id,
        )
        return

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            service = BacktestService(
                repository=BacktestRunRepository(session),
                prediction_service=get_prediction_service(session),
                training_job_service=get_training_job_service(session),
                max_steps=get_settings().max_backtest_steps,
            )
            await service.execute_run(run_id)
    except Exception:  # noqa: BLE001 - last-resort net, see docstring above
        logger.exception(
            "Backtest run %s crashed in its background task outside its own execute_run "
            "try/except; attempting to mark it failed",
            run_id,
        )
        await _mark_run_failed_after_crash(run_id, "Background backtest task crashed")


async def _mark_run_failed_after_crash(run_id: uuid.UUID, error_message: str) -> None:
    """Best-effort recovery write for a crash `execute_run` never got to handle itself.

    Mirrors `app.dependencies.training._mark_job_failed_after_crash` exactly,
    including keeping `get_engine()` inside this function's own `try` (not
    before it) — see that function's own docstring for why that placement
    matters. When this recovery write cannot run at all, the run is left
    exactly as the crash found it — most likely `'running'` — with only a
    log line, the same disclosed limitation training jobs already carry
    (see `ARCHITECTURE.md` § "Backtesting Engine").
    """
    try:
        engine = get_engine()
        if engine is None:
            return
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as session:
            repository = BacktestRunRepository(session)
            run = await repository.get_by_id(run_id)
            if run is not None and run.status == "running":
                await repository.update(
                    run,
                    {
                        "status": "failed",
                        "error_message": error_message,
                        "completed_at": datetime.now(UTC),
                    },
                )
    except Exception:  # noqa: BLE001 - best-effort only; already logged upstream
        logger.exception(
            "Also failed to mark backtest run %s failed after a background crash", run_id
        )


def schedule_backtest_run(run_id: uuid.UUID) -> None:
    """Fire-and-forget `run_backtest_in_background(run_id)`, tracked.

    Delegates to `app.services.background_tasks.schedule` — the exact same
    shared registry `schedule_training_job` uses, so `app/application.py`'s
    `shutdown()` cancels an in-flight backtest the same way it already
    cancels an in-flight training run, with no second tracking mechanism.
    """
    background_tasks.schedule(run_backtest_in_background(run_id), name=f"backtest-run-{run_id}")
