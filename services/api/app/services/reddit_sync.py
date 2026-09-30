"""Periodic catch-up synchronization of Reddit comments.

`RedditSyncScheduler` mirrors `app.services.news_sync.NewsSyncScheduler`'s
own shape exactly (a single asyncio task, one tick at a time, database-
optional, `run_catch_up`/`run_sync_once` naming): Reddit ingestion calls
`app.services.reddit_ingest.ingest_reddit` (persist rich comments, then
mirror two derived daily aggregates), never the generic connector-
agnostic `ingest_external_data` — see `ConnectorMetadata.auto_synced`'s
own docstring for why `RedditConnector` is excluded from the generic
scheduler entirely.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.connectors.reddit import REDDIT_VOLUME_SOURCE
from app.core.config import get_settings
from app.db.engine import get_engine
from app.repositories.reddit import RedditRepository
from app.services.connector_sync_runs import describe_failure, record_sync_run
from app.services.reddit_ingest import RedditIngestError, RedditIngestReport, ingest_reddit

logger = logging.getLogger("app.services.reddit_sync")

#: Unlike Marketaux's own `DISCOVERY_SAFETY_MARGIN` (needed because an
#: article can be *discovered* well after its own `published_at`), Reddit
#: comments were confirmed live to be queryable via Arctic Shift promptly
#: after creation (this module's own connector docstring, point 5) — the
#: only real lag found was in a *post's* own `score`/`num_comments`
#: fields, which this pipeline never reads. A small margin is still kept,
#: not zero, as a deliberate safety buffer against Arctic Shift's own
#: undocumented indexing latency (its README gives "no uptime or
#: performance guarantees") rather than assuming perfect immediacy.
DISCOVERY_SAFETY_MARGIN = timedelta(minutes=30)


@dataclass(frozen=True)
class RedditSyncTickSummary:
    """Outcome of one catch-up run."""

    attempted: int
    synced: int
    failed: int
    duration_seconds: float
    report: RedditIngestReport | None


class RedditSyncScheduler:
    """Periodic catch-up ingestion of Reddit comments.

    Args:
        interval_seconds: Delay between ticks.
        backfill_days: Window seeded when nothing is stored yet.
        max_window_days: Hard cap on any single tick's own window span —
            a wide gap (an empty table, or a scheduler restarted after
            days offline) is caught up gradually over several ticks
            instead of one unattended burst; see `_catch_up_window`.
    """

    def __init__(
        self,
        *,
        interval_seconds: int = 3600,
        backfill_days: int = 2,
        max_window_days: int = 2,
    ) -> None:
        self._interval_seconds = max(interval_seconds, 1)
        self._backfill_days = max(backfill_days, 1)
        self._max_window = timedelta(days=max(max_window_days, 1))
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
            logger.warning("Reddit sync scheduler not started: database not configured")
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._loop(), name="reddit-sync-loop")
        logger.info("Reddit sync scheduler started (interval=%ss)", self._interval_seconds)

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
        logger.info("Reddit sync scheduler stopped")

    async def _loop(self) -> None:
        """Run ticks back-to-back until stopped."""
        while not self._stopped.is_set():
            started = perf_counter()
            summary = await self.run_catch_up()
            if summary.attempted > 0:
                logger.info(
                    "Reddit sync tick: synced=%d failed=%d in %.2fs",
                    summary.synced,
                    summary.failed,
                    perf_counter() - started,
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_seconds)

    async def run_catch_up(self) -> RedditSyncTickSummary:
        """Sync Reddit comments up to now, or return a clean no-op if not configured."""
        started = perf_counter()
        window = await self._catch_up_window(datetime.now(UTC))
        if window is None:
            return RedditSyncTickSummary(0, 0, 0, perf_counter() - started, None)

        start, end = window
        attempt_started = datetime.now(UTC)
        try:
            report = await ingest_reddit(start=start, end=end)
        except RedditIngestError as exc:
            logger.error("Reddit sync failed: %s", exc)
            await record_sync_run(
                get_engine(),
                source=REDDIT_VOLUME_SOURCE,
                started_at=attempt_started,
                success=False,
                error_message=describe_failure(exc),
            )
            return RedditSyncTickSummary(1, 0, 1, perf_counter() - started, None)
        except Exception as exc:
            logger.exception("Reddit sync crashed")
            await record_sync_run(
                get_engine(),
                source=REDDIT_VOLUME_SOURCE,
                started_at=attempt_started,
                success=False,
                error_message=describe_failure(exc),
            )
            return RedditSyncTickSummary(1, 0, 1, perf_counter() - started, None)

        await record_sync_run(
            get_engine(),
            source=REDDIT_VOLUME_SOURCE,
            started_at=attempt_started,
            success=True,
            received=report.received,
            inserted=report.inserted,
            duplicates_skipped=report.duplicates_skipped,
            rejected=report.rejected,
            duration_seconds=report.duration_seconds,
        )
        return RedditSyncTickSummary(1, 1, 0, perf_counter() - started, report)

    async def _catch_up_window(self, now: datetime) -> tuple[datetime, datetime] | None:
        """Return `[start, end]` to sync, or `None` if the database is not
        configured. `start` never sits exactly at the newest stored
        comment's own `created_utc` — a small `DISCOVERY_SAFETY_MARGIN` is
        kept, mirroring `NewsSyncScheduler._catch_up_window`'s own shape
        for a smaller, deliberately-scoped reason (see this module's own
        docstring). Never returns `None` for "already caught up": a tick
        always re-checks at least the safety-margin window, deliberately.

        The returned span is never wider than `max_window_days`, regardless
        of how far `start` sits from `now` — an empty table, or a
        scheduler restarted after days offline, would otherwise hand one
        unattended tick a gap wide enough to trip Arctic Shift's own
        sustained-request rate limit (found for real backfilling this
        connector's own history; see `reddit_sync_backfill_days`'s own
        comment in `app.core.config`). A wide gap is caught up gradually,
        `max_window_days` at a time, one tick per interval, rather than in
        one burst — the next tick's own `start` is just wherever this
        one's clamped `end` landed, via the same `last_created_utc` read.
        """
        engine = get_engine()
        if engine is None:
            return None
        session = async_sessionmaker(bind=engine, expire_on_commit=False)()
        try:
            last_created_utc = await RedditRepository(session).get_latest_created_utc()
        finally:
            await session.close()

        if last_created_utc is None:
            start = now - timedelta(days=self._backfill_days)
        else:
            if last_created_utc.tzinfo is None:
                last_created_utc = last_created_utc.replace(tzinfo=UTC)
            start = min(last_created_utc, now - DISCOVERY_SAFETY_MARGIN)
        end = min(now, start + self._max_window)
        return start, end


async def run_sync_once() -> RedditSyncTickSummary:
    """Run one catch-up pass synchronously (CLI and manual verification)."""
    settings = get_settings()
    scheduler = RedditSyncScheduler(
        interval_seconds=settings.reddit_sync_interval_seconds,
        backfill_days=settings.reddit_sync_backfill_days,
        max_window_days=settings.reddit_sync_max_window_days,
    )
    return await scheduler.run_catch_up()
