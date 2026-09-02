"""Dependency providers for the Machine Learning Training Framework API.

Also owns the background-execution seam `POST /training-jobs/{id}/run`
uses so the request no longer blocks for the run's duration: this module
already knows how to build a `TrainingJobService` from a bare `AsyncSession`
(`get_training_job_service` below), which is exactly what's needed to build
a *second*, independent one bound to a session the background task opens
for itself — see `run_training_job_in_background`'s own docstring for why
that matters, and `app/services/candle_sync.py`'s `CandleSyncScheduler` for
the existing precedent this mirrors (a `get_engine()`-backed session, never
the request's own).
"""

import asyncio
import functools
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import get_engine
from app.db.session import get_db
from app.dependencies.ml_datasets import get_ml_dataset_service
from app.repositories.experiments import ExperimentRepository
from app.repositories.training import TrainingJobRepository
from app.services.experiments import ExperimentService
from app.services.training import TrainingJobService
from app.training.adapters import load_builtin_model_adapters
from app.training.pipeline import TrainingPipeline
from app.training.registry import default_registry as default_model_adapter_registry

logger = logging.getLogger("app.dependencies.training")

#: Every `asyncio.Task` currently executing a training job's pipeline in the
#: background, keyed by nothing (a plain set) since nothing here needs to
#: look one up by job id — only to cancel/await "all of them" on shutdown,
#: or await "all of them" deterministically in a test. A task discards
#: itself once done (`_track`'s own done-callback), so this never grows
#: unbounded across the process's lifetime.
_background_tasks: set[asyncio.Task[None]] = set()


@functools.lru_cache(maxsize=1)
def get_training_pipeline() -> TrainingPipeline:
    """Return the process-wide training pipeline."""
    load_builtin_model_adapters()
    return TrainingPipeline(default_model_adapter_registry)


def get_training_job_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TrainingJobService:
    """Build the training job service wired to the request session.

    Composes `ExperimentService` directly (not a second copy of it) so the
    "update experiment" pipeline stage reuses the exact same experiment
    mutation logic `/experiments` itself calls — see
    `app/services/training.py`'s module docstring.
    """
    return TrainingJobService(
        repository=TrainingJobRepository(session),
        experiment_service=ExperimentService(repository=ExperimentRepository(session)),
        pipeline=get_training_pipeline(),
        # The exact same `MLDatasetService` `/markets/{symbol}/ml/dataset` itself
        # uses — a `requires_real_data` adapter's `load_dataset` stage builds a
        # real dataset through this, never a second dataset-building path.
        ml_dataset_service=get_ml_dataset_service(session),
    )


async def run_training_job_in_background(job_id: uuid.UUID) -> None:
    """Run `TrainingJobService.execute_run` for `job_id` in a background task.

    Called (via `schedule_training_job`) only after the request has already
    moved the job to 'running' with its own session — that request's
    session is closed by the time this coroutine actually gets a turn on
    the event loop (`asyncio.create_task` schedules it, it does not run
    inline), so reusing it here would fail. Instead this opens a brand-new
    session bound to the same process-wide engine (`get_engine()`), exactly
    like `CandleSyncScheduler`'s own periodic ticks do (see
    `app/services/candle_sync.py`), and builds a second, independent
    `TrainingJobService` from it — never the request-scoped instance.

    `execute_run` already catches any exception the pipeline itself raises
    and marks the job 'failed' with the captured error (see its own
    docstring) — the `except Exception` below is a second, outer net for
    anything that goes wrong *outside* that call (failing to open the
    session, failing to build the service, or a bug in `execute_run`
    itself), so a background task's exception is never just logged nowhere
    and forgotten, the well-known failure mode of a bare
    `asyncio.create_task` whose result nobody ever awaits or checks.

    Deliberately does **not** catch `asyncio.CancelledError` (which is not
    an `Exception` subclass): a task cancelled by
    `cancel_in_flight_training_jobs` during app shutdown is meant to stop
    where it is, not be reinterpreted as a training failure — see that
    function's own docstring for the resulting, disclosed limitation.
    """
    engine = get_engine()
    if engine is None:
        logger.error(
            "Cannot execute training job %s in background: database is not configured",
            job_id,
        )
        return

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            service = TrainingJobService(
                repository=TrainingJobRepository(session),
                experiment_service=ExperimentService(repository=ExperimentRepository(session)),
                pipeline=get_training_pipeline(),
                ml_dataset_service=get_ml_dataset_service(session),
            )
            await service.execute_run(job_id)
    except Exception:  # noqa: BLE001 - last-resort net, see docstring above
        logger.exception(
            "Training job %s crashed in its background task outside its own pipeline "
            "try/except; attempting to mark it failed",
            job_id,
        )
        await _mark_job_failed_after_crash(job_id, "Background training task crashed")


async def _mark_job_failed_after_crash(job_id: uuid.UUID, error_message: str) -> None:
    """Best-effort recovery write for a crash `execute_run` never got to handle itself.

    Opens yet another brand-new session — the one `run_training_job_in_background`
    was using when it crashed may be in an unusable state, so this never
    reuses it. Only touches the job if it is still 'running' (not already
    finalized by some other path), and swallows its own failure: the
    original crash is already logged by the caller, and this is a
    best-effort cleanup, not something that should raise a second exception
    out of a background task.

    Called from inside `run_training_job_in_background`'s own `except`
    block, which means a second exception raised directly out of *this*
    function (not caught here first) would propagate out of that `except`
    uncaught — an exception cannot be caught by the same `except` clause
    that is already handling one. So `get_engine()` itself raising (not
    just returning `None`) is deliberately inside this function's own
    `try`, not before it, even though every other call site in this module
    checks `get_engine() is None` before entering a `try` — this is the one
    place that distinction would otherwise let a background task's
    exception escape silently again, the exact failure mode this whole
    module exists to prevent. When this recovery write cannot run at all
    (no engine, or `get_engine()`/the session raise), the job is left
    exactly as the crash found it — most likely `'running'` — with only a
    log line, no further escalation; see the disclosed limitation in
    `ARCHITECTURE.md` § "Machine Learning Training Framework".
    """
    try:
        engine = get_engine()
        if engine is None:
            return
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as session:
            repository = TrainingJobRepository(session)
            job = await repository.get_by_id(job_id)
            if job is not None and job.status == "running":
                await repository.update(
                    job,
                    {
                        "status": "failed",
                        "error_message": error_message,
                        "completed_at": datetime.now(UTC),
                    },
                )
    except Exception:  # noqa: BLE001 - best-effort only; already logged upstream
        logger.exception(
            "Also failed to mark training job %s failed after a background crash", job_id
        )


def _track(task: asyncio.Task[None]) -> None:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def schedule_training_job(job_id: uuid.UUID) -> None:
    """Fire-and-forget `run_training_job_in_background(job_id)`, tracked.

    Tracking (rather than a bare `asyncio.create_task` the caller discards)
    serves two purposes: `cancel_in_flight_training_jobs` can cancel/await
    every in-flight run on app shutdown (mirroring
    `CandleSyncScheduler.stop`'s own cancel-then-await pattern, generalized
    to a dynamic set of per-request tasks instead of one persistent loop
    task), and `wait_for_in_flight_training_jobs` gives tests a
    deterministic way to await background execution instead of a real
    sleep-based poll.
    """
    task = asyncio.create_task(run_training_job_in_background(job_id), name=f"train-run-{job_id}")
    _track(task)


async def cancel_in_flight_training_jobs() -> None:
    """Cancel and await every training job still executing in the background.

    Called from `app/application.py`'s `shutdown()`, before the database
    engine is disposed — the same relative ordering `Runtime.shutdown`
    already uses for `CandleSyncScheduler.stop()` (stop the thing that uses
    the engine, then dispose the engine).

    Unlike `CandleSyncScheduler`, whose single loop task waits on an
    `asyncio.Event` at a safe boundary between ticks, a training run's
    background task is cancelled at whatever `await` point it happens to be
    at — mid-pipeline-stage, mid-DB-write, anywhere. `asyncio.CancelledError`
    is not an `Exception` subclass, so it is **not** caught by
    `execute_run`'s own `except Exception` (see `run_training_job_in_background`'s
    docstring) — a cancelled task never gets the chance to mark its job
    'failed' the normal way. The disclosed, real limitation this leaves: a
    training job whose background task was still running at shutdown time
    is left with `status='running'` in the database, and there is no
    restart-recovery/watchdog in this platform yet to reconcile it — the
    same "no worker/queue service exists yet" limitation this whole feature
    already lives with (see `ARCHITECTURE.md` § "Machine Learning Training
    Framework"), not a new one this change introduces.
    """
    tasks = list(_background_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def wait_for_in_flight_training_jobs() -> None:
    """Await every currently-tracked background training task to completion.

    Test-only helper: the deterministic alternative to a real sleep-based
    poll for "has the background run finished yet" — see
    `services/api/TESTING.md` § "Testing the non-blocking training run"
    for how the test suite uses this alongside monkeypatching `get_engine`
    to the test's own in-memory engine (mirroring
    `tests/services/test_candle_sync.py`'s existing convention for the
    same reason: this module's background task never goes through
    `get_db`/FastAPI's dependency overrides).
    """
    tasks = list(_background_tasks)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
