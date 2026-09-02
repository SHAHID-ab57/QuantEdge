"""Periodic grading of predictions whose target horizon has arrived.

Mirrors `app.services.candle_sync.CandleSyncScheduler` exactly: a single
`asyncio` loop task, its own database session per tick (never a
request-scoped one — there is no request here), an enable flag, isolated
failures, and `run_grading_once` — a synchronous one-off entry point for
ops/manual verification, the same role `run_sync_once` plays for candle
sync. No new queue or message broker; grading one prediction is fast (a
few small DB reads plus one already-fast `TargetPipeline.run` call), the
same "no worker/queue service needed" reasoning `PredictionService.run`'s
own docstring already gives for live inference itself.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.engine import get_engine
from app.dependencies.prediction import get_prediction_service
from app.services.prediction import GradingSummary

logger = logging.getLogger("app.services.grading_scheduler")


@dataclass(frozen=True)
class GradingTickSummary:
    """Outcome of one grading pass, plus how long it took."""

    attempted: int
    graded: int
    not_yet_knowable: int
    failed: int
    duration_seconds: float


class PredictionGradingScheduler:
    """Periodic grading of every prediction whose target horizon has arrived.

    Args:
        interval_seconds: Delay between ticks.
    """

    def __init__(self, *, interval_seconds: int = 300) -> None:
        self._interval_seconds = max(interval_seconds, 1)
        self._stopped = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        """True while the background loop task is alive."""
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Begin the periodic loop, running the first tick immediately."""
        if self.running:
            return
        if get_engine() is None:
            logger.warning("Prediction grading scheduler not started: database is not configured")
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._loop(), name="prediction-grading-loop")
        logger.info("Prediction grading scheduler started (interval=%ss)", self._interval_seconds)

    async def stop(self) -> None:
        """Stop the loop, cancelling any in-flight tick."""
        task = self._task
        if task is None:
            return
        self._stopped.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None
        logger.info("Prediction grading scheduler stopped")

    async def _loop(self) -> None:
        """Run ticks back-to-back until stopped."""
        while not self._stopped.is_set():
            started = perf_counter()
            summary = await self.run_grading_tick()
            if summary.attempted > 0:
                logger.info(
                    "Prediction grading tick: graded=%d not_yet_knowable=%d failed=%d in %.2fs",
                    summary.graded,
                    summary.not_yet_knowable,
                    summary.failed,
                    perf_counter() - started,
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_seconds)

    async def run_grading_tick(self) -> GradingTickSummary:
        """Grade every currently-knowable pending prediction, once.

        Opens its own session bound to the process-wide engine — exactly
        the `get_engine()`-backed pattern `CandleSyncScheduler` already
        uses for its own ticks, never a request-scoped session (there is
        no request here).
        """
        started = perf_counter()
        engine = get_engine()
        if engine is None:
            logger.warning("Prediction grading skipped: database is not configured")
            return GradingTickSummary(0, 0, 0, 0, 0.0)

        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as session:
            service = get_prediction_service(session)
            summary: GradingSummary = await service.grade_pending()

        return GradingTickSummary(
            attempted=summary.attempted,
            graded=summary.graded,
            not_yet_knowable=summary.not_yet_knowable,
            failed=summary.failed,
            duration_seconds=perf_counter() - started,
        )


async def run_grading_once() -> GradingTickSummary:
    """Run one grading pass synchronously (CLI and manual verification)."""
    scheduler = PredictionGradingScheduler()
    summary = await scheduler.run_grading_tick()
    logger.info(
        "Prediction grading run completed: graded=%d not_yet_knowable=%d failed=%d in %.2fs",
        summary.graded,
        summary.not_yet_knowable,
        summary.failed,
        summary.duration_seconds,
    )
    return summary
