"""Periodic catch-up synchronization of news articles.

`NewsSyncScheduler` mirrors `app.services.external_data_sync
.ExternalDataSyncScheduler`'s own shape (a single asyncio task, one tick
at a time, database-optional, `run_catch_up`/`run_sync_once` naming) but
is a genuinely *separate* class, not a reuse of that one: news ingestion
calls `app.services.news_ingest.ingest_news` (persist rich articles into
`news_articles`, then mirror a derived daily aggregate), never the
generic connector-agnostic `ingest_external_data` — see
`ConnectorMetadata.auto_synced`'s own docstring for why Marketaux is
excluded from the generic scheduler entirely.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.db.engine import get_engine
from app.repositories.news import NewsRepository
from app.services.news_ingest import NewsIngestError, NewsIngestReport, ingest_news

logger = logging.getLogger("app.services.news_sync")

#: Sized to at least one full tick interval (`news_sync_interval_seconds`'s
#: own default, 6h) — see `app.connectors.marketaux`'s own module
#: docstring for the discovery-latency risk this margin exists to catch:
#: an article whose own indexing lands *after* `published_at`, for a
#: window an earlier, tighter tick had already moved past. A margin this
#: wide guarantees no gap can open between two consecutive ticks' own
#: windows even if discovery is delayed by up to that long — not an
#: arbitrary number, sized directly from the scheduler's own real cadence.
DISCOVERY_SAFETY_MARGIN = timedelta(hours=6)


@dataclass(frozen=True)
class NewsSyncTickSummary:
    """Outcome of one catch-up run."""

    attempted: int
    synced: int
    failed: int
    duration_seconds: float
    report: NewsIngestReport | None


class NewsSyncScheduler:
    """Periodic catch-up ingestion of Marketaux news.

    Args:
        interval_seconds: Delay between ticks.
        backfill_days: Window seeded when nothing is stored yet.
    """

    def __init__(
        self,
        *,
        interval_seconds: int = 21600,
        backfill_days: int = 3650,
    ) -> None:
        self._interval_seconds = max(interval_seconds, 1)
        self._backfill_days = max(backfill_days, 1)
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
            logger.warning("News sync scheduler not started: database not configured")
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._loop(), name="news-sync-loop")
        logger.info("News sync scheduler started (interval=%ss)", self._interval_seconds)

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
        logger.info("News sync scheduler stopped")

    async def _loop(self) -> None:
        """Run ticks back-to-back until stopped."""
        while not self._stopped.is_set():
            started = perf_counter()
            summary = await self.run_catch_up()
            if summary.attempted > 0:
                logger.info(
                    "News sync tick: synced=%d failed=%d in %.2fs",
                    summary.synced,
                    summary.failed,
                    perf_counter() - started,
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_seconds)

    async def run_catch_up(self) -> NewsSyncTickSummary:
        """Sync news up to now, or return a clean no-op if not configured."""
        started = perf_counter()
        window = await self._catch_up_window(datetime.now(UTC))
        if window is None:
            return NewsSyncTickSummary(0, 0, 0, perf_counter() - started, None)

        start, end = window
        try:
            report = await ingest_news(start=start, end=end)
        except NewsIngestError as exc:
            logger.error("News sync failed: %s", exc)
            return NewsSyncTickSummary(1, 0, 1, perf_counter() - started, None)
        except Exception:
            logger.exception("News sync crashed")
            return NewsSyncTickSummary(1, 0, 1, perf_counter() - started, None)

        return NewsSyncTickSummary(1, 1, 0, perf_counter() - started, report)

    async def _catch_up_window(self, now: datetime) -> tuple[datetime, datetime] | None:
        """Return `[start, end]` to sync, or `None` if the database is not
        configured. Unlike `ExternalDataSyncScheduler._catch_up_window`,
        `start` is never pinned to exactly the newest stored article's own
        `published_at` — see `DISCOVERY_SAFETY_MARGIN`'s own comment for
        why a bare floor there is the wrong choice for this specific
        source. Never returns `None` for "already caught up": a tick
        always re-checks at least the safety-margin window, deliberately.
        """
        engine = get_engine()
        if engine is None:
            return None
        session = async_sessionmaker(bind=engine, expire_on_commit=False)()
        try:
            last_published_at = await NewsRepository(session).get_latest_published_at()
        finally:
            await session.close()

        if last_published_at is None:
            start = now - timedelta(days=self._backfill_days)
        else:
            if last_published_at.tzinfo is None:
                last_published_at = last_published_at.replace(tzinfo=UTC)
            start = min(last_published_at, now - DISCOVERY_SAFETY_MARGIN)
        return start, now


async def run_sync_once() -> NewsSyncTickSummary:
    """Run one catch-up pass synchronously (CLI and manual verification)."""
    settings = get_settings()
    scheduler = NewsSyncScheduler(
        interval_seconds=settings.news_sync_interval_seconds,
        backfill_days=settings.news_sync_backfill_days,
    )
    return await scheduler.run_catch_up()
