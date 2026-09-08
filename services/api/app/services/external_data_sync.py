"""Periodic catch-up synchronization of external data points.

The :class:`ExternalDataSyncScheduler` keeps `external_data_points` current
by re-running the existing, idempotent
:func:`~app.services.external_data_ingest.ingest_external_data` path on a
schedule — mirroring `app.services.candle_sync.CandleSyncScheduler`
exactly: for every configured connector source it fills the window from
the newest stored point to now. Because ingestion checks existing
timestamps before inserting, repeated ticks are safe and never create
duplicates.

The scheduler runs as a single asyncio task (one tick at a time); when the
database is not configured it degrades to a no-op with a warning. Failures
are isolated per source so one broken connector never stops the rest.
"""

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.connectors import load_builtin_connectors
from app.connectors.registry import default_registry as default_connector_registry
from app.core.config import get_settings
from app.db.engine import get_engine
from app.models.external_data import ExternalDataPoint
from app.services.external_data_ingest import (
    ExternalDataIngestError,
    ExternalDataIngestReport,
    ingest_external_data,
)

logger = logging.getLogger("app.services.external_data_sync")


@dataclass(frozen=True)
class ExternalDataSyncTickSummary:
    """Outcome of one catch-up run, across every configured source."""

    attempted: int
    synced: int
    failed: int
    duration_seconds: float
    reports: tuple[ExternalDataIngestReport, ...]


class ExternalDataSyncScheduler:
    """Periodic catch-up ingestion of every configured connector source.

    Args:
        sources: Connector source names to keep current; when empty,
            every registered connector (mirrors `candle_sync_symbols`'s
            own "empty means resolve a sensible default" convention).
        interval_seconds: Delay between ticks.
        backfill_days: Window seeded for a source with no stored points yet.
    """

    def __init__(
        self,
        *,
        sources: Sequence[str] | None = None,
        interval_seconds: int = 3600,
        backfill_days: int = 3650,
    ) -> None:
        self._sources = list(sources) if sources is not None else None
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
            logger.warning("External data sync scheduler not started: database not configured")
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._loop(), name="external-data-sync-loop")
        logger.info("External data sync scheduler started (interval=%ss)", self._interval_seconds)

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
        logger.info("External data sync scheduler stopped")

    async def _loop(self) -> None:
        """Run ticks back-to-back until stopped."""
        while not self._stopped.is_set():
            started = perf_counter()
            summary = await self.run_catch_up()
            if summary.attempted > 0:
                logger.info(
                    "External data sync tick: synced=%d failed=%d in %.2fs",
                    summary.synced,
                    summary.failed,
                    perf_counter() - started,
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_seconds)

    async def run_catch_up(self) -> ExternalDataSyncTickSummary:
        """Sync every configured source up to now.

        One run covers all sources; a failing source is logged and does
        not stop the remaining ones.
        """
        started = perf_counter()
        load_builtin_connectors()
        sources = self._target_sources()
        if not sources:
            return ExternalDataSyncTickSummary(0, 0, 0, 0.0, ())

        reports: list[ExternalDataIngestReport] = []
        synced = 0
        failed = 0
        now = datetime.now(UTC)
        for source in sources:
            try:
                window = await self._catch_up_window(source, now)
            except Exception as exc:
                failed += 1
                logger.error("External data sync failed to plan %s: %s", source, exc)
                continue
            if window is None:
                continue
            start, end = window
            try:
                report = await ingest_external_data(source=source, start=start, end=end)
                reports.append(report)
                synced += 1
            except ExternalDataIngestError as exc:
                failed += 1
                logger.error("External data sync failed for %s: %s", source, exc)
            except Exception:
                failed += 1
                logger.exception("External data sync crashed for %s", source)

        return ExternalDataSyncTickSummary(
            attempted=len(sources),
            synced=synced,
            failed=failed,
            duration_seconds=perf_counter() - started,
            reports=tuple(reports),
        )

    def _target_sources(self) -> list[str]:
        """Resolve which connector sources this scheduler keeps current.

        Excludes any registered source whose own `ConnectorMetadata
        .auto_synced` is `False` — even an explicit `sources=` override
        can't force one through, since the exclusion means this generic
        "fetch one point, persist it straight into external_data_points"
        tick is structurally the wrong pipeline for that source's own
        shape (see `auto_synced`'s own docstring).
        """
        configured = self._sources
        if not configured:
            settings = get_settings()
            configured = [
                part.strip()
                for part in settings.external_data_sync_sources.split(",")
                if part.strip()
            ] or list(default_connector_registry.names())

        known = [source for source in configured if default_connector_registry.has(source)]
        missing = [source for source in configured if source not in known]
        if missing:
            logger.warning("External data sync skipping unknown sources: %s", ", ".join(missing))
        auto_synced = [
            source for source in known if default_connector_registry.describe(source).auto_synced
        ]
        return sorted(auto_synced)

    async def _catch_up_window(
        self, source: str, now: datetime
    ) -> tuple[datetime, datetime] | None:
        """Return `[start, end]` to sync, or `None` if already fully caught up.

        `end` is always `now` — unlike candle buckets, an external data
        point has no "closed bucket" boundary to wait for; the connector
        itself decides what it actually has available as of `now`. When
        nothing is stored yet, `start` is seeded with the configured
        backfill window.
        """
        engine = get_engine()
        if engine is None:
            return None
        session = async_sessionmaker(bind=engine, expire_on_commit=False)()
        try:
            last_timestamp = (
                await session.execute(
                    select(func.max(ExternalDataPoint.timestamp)).where(
                        ExternalDataPoint.source == source
                    )
                )
            ).scalar()
        finally:
            await session.close()

        if last_timestamp is None:
            start = now - timedelta(days=self._backfill_days)
        else:
            if last_timestamp.tzinfo is None:
                last_timestamp = last_timestamp.replace(tzinfo=UTC)
            start = last_timestamp
            if start >= now:
                return None
        return start, now


async def run_sync_once(sources: Sequence[str] | None = None) -> ExternalDataSyncTickSummary:
    """Run one catch-up pass synchronously (CLI and manual verification)."""
    scheduler = ExternalDataSyncScheduler(sources=sources)
    summary = await scheduler.run_catch_up()
    logger.info(
        "External data sync run completed: synced=%d failed=%d in %.2fs",
        summary.synced,
        summary.failed,
        summary.duration_seconds,
    )
    for report in summary.reports:
        logger.info(
            "External data sync %s: received=%d inserted=%d duplicates_skipped=%d rejected=%d",
            report.source,
            report.received,
            report.inserted,
            report.duplicates_skipped,
            report.rejected,
        )
    return summary
