"""Standalone entrypoint for the independent, DB/REST-only background schedulers.

Runs `CandleSyncScheduler`, `PredictionGradingScheduler`,
`ExternalDataSyncScheduler`, `NewsSyncScheduler`, and `RetrainingScheduler` in
their own process, off the API's request-serving event loop — see
`docs/infrastructure/EVENT_LOOP_SEPARATION_DESIGN.md` (Option 3, accepted)
for why. These five have no dependency on the live WS-fed
`EventBus`/`MarketStateManager` (confirmed from their constructor signatures
in `app.runtime.Runtime.start`), unlike `StopLossTakeProfitMonitor`,
`OrderFlowCapture`, and the two paper-trading schedulers, which stay in
`api` because separating them would require a live-state bridge that is
deliberately out of scope here.

Usage: ``python -m app.scheduler_main`` (see `docker-compose.yml`'s
``scheduler`` service). Not started via `uvicorn` — this process serves no
HTTP; liveness is a heartbeat file (`HEARTBEAT_PATH`) touched on a fixed
interval, checked by a `docker healthcheck` that verifies the file's
recency rather than probing a port.
"""

import asyncio
import contextlib
import logging
import signal
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.env_validation import find_duplicate_env_keys, raise_for_conflicting_duplicates
from app.core.logging import setup_logging
from app.db.engine import dispose_engine, get_engine, probe_database
from app.services.candle_sync import CandleSyncScheduler
from app.services.external_data_sync import ExternalDataSyncScheduler
from app.services.grading_scheduler import PredictionGradingScheduler
from app.services.news_sync import NewsSyncScheduler
from app.services.retraining import RetrainingScheduler, RetrainingTarget

logger = logging.getLogger("app.scheduler_main")

HEARTBEAT_PATH = Path("/app/var/scheduler_heartbeat")
HEARTBEAT_INTERVAL_SECONDS = 15


@dataclass
class Schedulers:
    """Whichever of the five independent schedulers are enabled — `None`
    for a disabled one, mirroring `Runtime`'s own `X | None` attribute
    pattern, just held in one small container instead of five separate
    instance attributes since there's no `Runtime` object here to hang
    them off."""

    candle_sync: CandleSyncScheduler | None = None
    prediction_grading: PredictionGradingScheduler | None = None
    external_data_sync: ExternalDataSyncScheduler | None = None
    news_sync: NewsSyncScheduler | None = None
    retraining: RetrainingScheduler | None = None


async def _start_schedulers(settings: Settings) -> Schedulers:
    """Build and start whichever of the five schedulers are enabled — the
    exact same construction `app.runtime.Runtime.start` used to do for
    these five, unmodified."""
    schedulers = Schedulers()
    if settings.candle_sync_enabled:
        schedulers.candle_sync = CandleSyncScheduler(
            interval_seconds=settings.candle_sync_interval_seconds,
            backfill_days=settings.candle_sync_backfill_days,
        )
        await schedulers.candle_sync.start()
    if settings.prediction_grading_enabled:
        schedulers.prediction_grading = PredictionGradingScheduler(
            interval_seconds=settings.prediction_grading_interval_seconds,
        )
        await schedulers.prediction_grading.start()
    if settings.external_data_sync_enabled:
        configured_sources = [
            part.strip()
            for part in settings.external_data_sync_sources.split(",")
            if part.strip()
        ] or None
        schedulers.external_data_sync = ExternalDataSyncScheduler(
            sources=configured_sources,
            interval_seconds=settings.external_data_sync_interval_seconds,
            backfill_days=settings.external_data_sync_backfill_days,
        )
        await schedulers.external_data_sync.start()
    if settings.news_sync_enabled:
        schedulers.news_sync = NewsSyncScheduler(
            interval_seconds=settings.news_sync_interval_seconds,
            backfill_days=settings.news_sync_backfill_days,
        )
        await schedulers.news_sync.start()
    if settings.retraining_scheduler_enabled:
        retraining_targets = [
            RetrainingTarget(experiment_id=uuid.UUID(part.strip()))
            for part in settings.retraining_experiment_ids.split(",")
            if part.strip()
        ]
        schedulers.retraining = RetrainingScheduler(
            targets=retraining_targets,
            window_hours=settings.retraining_window_hours,
            min_retrain_interval_seconds=settings.retraining_min_interval_seconds,
            tick_interval_seconds=settings.retraining_tick_interval_seconds,
        )
        await schedulers.retraining.start()
    return schedulers


async def _stop_schedulers(schedulers: Schedulers) -> None:
    """Stop whichever of the five were actually started."""
    if schedulers.candle_sync is not None:
        await schedulers.candle_sync.stop()
    if schedulers.prediction_grading is not None:
        await schedulers.prediction_grading.stop()
    if schedulers.external_data_sync is not None:
        await schedulers.external_data_sync.stop()
    if schedulers.news_sync is not None:
        await schedulers.news_sync.stop()
    if schedulers.retraining is not None:
        await schedulers.retraining.stop()


async def _heartbeat_loop(stop: asyncio.Event) -> None:
    """Touch `HEARTBEAT_PATH` every `HEARTBEAT_INTERVAL_SECONDS` while the
    event loop is actually responsive. This is a coarser signal than "all
    five schedulers ticked recently" deliberately — `RetrainingScheduler`
    alone can go up to an hour between ticks by design, which would make a
    per-scheduler heartbeat indistinguishable from a hang. A dedicated,
    short-interval loop proves the loop itself is alive without waiting on
    any scheduler's own cadence.
    """
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    while not stop.is_set():
        HEARTBEAT_PATH.write_text(str(time.time()))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)


async def run(stop: asyncio.Event | None = None) -> int:
    """Start the five schedulers, then block until `stop` is set.

    `stop` is normally left as `None`, in which case a fresh `asyncio.Event`
    is created and wired to SIGINT/SIGTERM — the real production path. Tests
    pass an already-constructed (and often pre-set) `Event` instead, so a
    full start/shutdown cycle can run deterministically without touching
    process signals at all.
    """
    setup_logging()
    raise_for_conflicting_duplicates(find_duplicate_env_keys(".env"), logger=logger)
    settings = get_settings()
    logger.info(
        "Scheduler process configuration: candle_sync_enabled=%s "
        "prediction_grading_enabled=%s external_data_sync_enabled=%s "
        "news_sync_enabled=%s retraining_scheduler_enabled=%s "
        "retraining_experiment_ids=%r",
        settings.candle_sync_enabled,
        settings.prediction_grading_enabled,
        settings.external_data_sync_enabled,
        settings.news_sync_enabled,
        settings.retraining_scheduler_enabled,
        settings.retraining_experiment_ids,
    )
    if settings.retraining_scheduler_enabled and not settings.retraining_experiment_ids.strip():
        logger.warning(
            "retraining_experiment_ids is empty while retraining_scheduler_enabled is "
            "true: the scheduler will tick on schedule but retrain no lineage at all."
        )

    if get_engine() is None:
        raise RuntimeError(
            "DATABASE_URL is not configured. This process only runs DB-backed "
            "schedulers -- there is nothing for it to do without a database, "
            "unlike `api`, which still serves health/dev endpoints without one."
        )
    logger.info("Verifying database connection...")
    error = await probe_database()
    if error is not None:
        raise RuntimeError(f"Database connection failed: {error}")
    logger.info("Database connection established")

    schedulers = await _start_schedulers(settings)
    logger.info("Scheduler process startup complete")

    if stop is None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, stop.set)
        loop.add_signal_handler(signal.SIGTERM, stop.set)
    heartbeat_task = asyncio.create_task(_heartbeat_loop(stop), name="scheduler-heartbeat")

    await stop.wait()
    logger.info("Scheduler process shutting down...")

    heartbeat_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await heartbeat_task
    await _stop_schedulers(schedulers)
    await dispose_engine()
    logger.info("Scheduler process shutdown complete")
    return 0


def main() -> int:
    """Entry point."""
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
