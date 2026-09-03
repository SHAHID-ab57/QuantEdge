"""Shared fire-and-forget background-task registry.

The one place any fire-and-forget `asyncio.Task` this application starts
outside a request's own lifetime — a training run, a backtest — gets
tracked, for two reasons: `cancel_all` lets `app/application.py`'s
shutdown cancel every one of them cleanly before the database engine is
disposed (mirroring `CandleSyncScheduler.stop()`'s own cancel-then-await
pattern), and `wait_for_all` gives tests a deterministic way to await
completion instead of a real sleep-based poll.

Originally built inside `app/dependencies/training.py` for the training-job
non-blocking `POST /training-jobs/{id}/run` alone; extracted here once
`app/backtest/` needed the identical mechanism for `POST /backtests/run`,
rather than a second copy of it. `app.dependencies.training` still exposes
its own `schedule_training_job`/`cancel_in_flight_training_jobs`/
`wait_for_in_flight_training_jobs` names (nothing importing those needed to
change), but they now delegate here — there has only ever been one
registry, one cancel-all, and one wait-for-all since this module existed.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

#: Every `asyncio.Task` currently running in the background, keyed by
#: nothing (a plain set) since nothing here needs to look one up by id —
#: only to cancel/await "all of them" on shutdown, or await "all of them"
#: deterministically in a test. A task discards itself once done (`track`'s
#: own done-callback), so this never grows unbounded across the process's
#: lifetime.
_tasks: set[asyncio.Task[None]] = set()


def track(task: asyncio.Task[None]) -> None:
    """Register a fire-and-forget task so shutdown/tests can find it."""
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def schedule(coro: Coroutine[Any, Any, None], *, name: str) -> asyncio.Task[None]:
    """Fire-and-forget `coro` as a tracked background task."""
    task = asyncio.create_task(coro, name=name)
    track(task)
    return task


async def cancel_all() -> None:
    """Cancel and await every currently-tracked background task.

    Called from `app/application.py`'s `shutdown()`, before the database
    engine is disposed — the same relative ordering `Runtime.shutdown`
    already uses for `CandleSyncScheduler.stop()` (stop the thing that uses
    the engine, then dispose the engine). Cancels *every* tracked task
    regardless of which caller scheduled it (a training run, a backtest) —
    one registry, one shutdown path.

    A task is cancelled at whatever `await` point it happens to be at —
    mid-pipeline-stage, mid-DB-write, anywhere. `asyncio.CancelledError` is
    not an `Exception` subclass, so a task's own `except Exception` (if it
    has one) never sees it — a cancelled task never gets the chance to
    mark whatever it was doing as 'failed' the normal way. The disclosed,
    real limitation this leaves: a training job or backtest whose
    background task was still running at shutdown time is left in
    whatever state the crash found it, with no restart-recovery/watchdog
    in this platform yet to reconcile it — the same "no worker/queue
    service exists yet" limitation those features already live with, not a
    new one this registry introduces.
    """
    tasks = list(_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def wait_for_all() -> None:
    """Await every currently-tracked background task to completion.

    Test-only helper: the deterministic alternative to a real sleep-based
    poll for "has the background run finished yet".
    """
    tasks = list(_tasks)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
