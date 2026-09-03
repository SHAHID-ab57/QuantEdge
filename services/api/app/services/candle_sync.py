"""Periodic catch-up synchronization of historical OHLCV candles.

The :class:`CandleSyncScheduler` keeps the ``candles`` table current by
re-running the existing, idempotent :func:`~app.services.candle_ingest.ingest_candles`
path on a schedule: for every tracked symbol and configured timeframe it
fills the window from the newest stored candle to the most recently closed
bucket. Because ingestion validates buckets and skips rows whose open time
already exists, repeated ticks are safe and never create duplicates.

The scheduler runs as a single asyncio task (one tick at a time); when the
database is not configured it degrades to a no-op with a warning. Failures
are isolated per symbol/timeframe pair so one broken upstream never stops
the rest of the catalog.
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

from app.core.config import get_settings
from app.db.engine import get_engine
from app.models.candle import Candle
from app.models.market import Market
from app.services.candle_ingest import (
    DELTA_RESOLUTIONS,
    CandleIngestError,
    IngestReport,
    ingest_candles,
    resolution_duration,
)

logger = logging.getLogger("app.services.candle_sync")

DEFAULT_TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")


@dataclass(frozen=True)
class SyncTickSummary:
    """Outcome of one catch-up run."""

    attempted: int
    synced: int
    skipped: int
    failed: int
    duration_seconds: float
    reports: tuple[IngestReport, ...]


class CandleSyncScheduler:
    """Periodic catch-up ingestion of closed OHLCV candles.

    Args:
        symbols: Market symbols to keep current; when empty, symbols are
            resolved from ``candle_sync_symbols`` / ``delta_market_symbols``.
        timeframes: Candle resolutions to synchronize.
        interval_seconds: Delay between ticks.
        backfill_days: Window seeded for a symbol/timeframe with no stored
            candles yet.
    """

    def __init__(
        self,
        *,
        symbols: Sequence[str] | None = None,
        timeframes: Sequence[str] | None = None,
        interval_seconds: int = 300,
        backfill_days: int = 7,
    ) -> None:
        self._symbols = list(symbols) if symbols is not None else None
        self._timeframes = tuple(
            timeframe
            for timeframe in (timeframes or DEFAULT_TIMEFRAMES)
            if timeframe in DELTA_RESOLUTIONS
        )
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
            logger.warning("Candle sync scheduler not started: database is not configured")
            return
        if not self._timeframes:
            logger.warning("Candle sync scheduler not started: no supported timeframes")
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._loop(), name="candle-sync-loop")
        logger.info(
            "Candle sync scheduler started (interval=%ss, timeframes=%s)",
            self._interval_seconds,
            ",".join(self._timeframes),
        )

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
        logger.info("Candle sync scheduler stopped")

    async def _loop(self) -> None:
        """Run ticks back-to-back until stopped."""
        while not self._stopped.is_set():
            started = perf_counter()
            summary = await self.run_catch_up()
            if summary.attempted > 0:
                logger.info(
                    "Candle sync tick: synced=%d skipped=%d failed=%d in %.2fs",
                    summary.synced,
                    summary.skipped,
                    summary.failed,
                    perf_counter() - started,
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_seconds)

    async def run_catch_up(self) -> SyncTickSummary:
        """Sync every configured symbol/timeframe up to the last closed bucket.

        One run covers all pairs; a failing pair is logged and does not stop
        the remaining pairs.
        """
        started = perf_counter()
        pairs = await self._target_pairs()
        if not pairs:
            return SyncTickSummary(0, 0, 0, 0, 0.0, ())

        reports: list[IngestReport] = []
        synced = 0
        skipped = 0
        failed = 0
        for symbol, timeframe in pairs:
            try:
                window = await self._catch_up_window(symbol, timeframe)
            except Exception as exc:
                failed += 1
                logger.error("Candle sync failed to plan %s %s: %s", symbol, timeframe, exc)
                continue
            if window is None:
                skipped += 1
                continue
            start, end = window
            try:
                report = await ingest_candles(
                    symbol=symbol, timeframe=timeframe, start=start, end=end
                )
                reports.append(report)
                synced += 1
            except (CandleIngestError, RuntimeError) as exc:
                failed += 1
                logger.error("Candle sync failed for %s %s: %s", symbol, timeframe, exc)
            except Exception as exc:
                failed += 1
                logger.exception("Candle sync crashed for %s %s: %s", symbol, timeframe, exc)

        return SyncTickSummary(
            attempted=len(pairs),
            synced=synced,
            skipped=skipped,
            failed=failed,
            duration_seconds=perf_counter() - started,
            reports=tuple(reports),
        )

    async def _target_pairs(self) -> list[tuple[str, str]]:
        """Resolve (symbol, timeframe) pairs that exist in the database."""
        engine = get_engine()
        if engine is None:
            logger.warning("Candle sync skipped: database is not configured")
            return []

        settings = get_settings()
        configured = self._symbols
        if not configured:
            configured = [
                part.strip()
                for part in (settings.candle_sync_symbols or settings.delta_market_symbols).split(
                    ","
                )
                if part.strip()
            ]

        session = async_sessionmaker(bind=engine, expire_on_commit=False)()
        try:
            rows = await session.execute(
                select(Market.symbol).where(
                    Market.symbol.in_(configured), Market.is_active.is_(True)
                )
            )
            known = set(rows.scalars())
        finally:
            await session.close()

        missing = [symbol for symbol in configured if symbol not in known]
        if missing:
            logger.warning("Candle sync skipping unknown markets: %s", ", ".join(missing))
        return [(symbol, timeframe) for symbol in sorted(known) for timeframe in self._timeframes]

    async def _catch_up_window(
        self, symbol: str, timeframe: str
    ) -> tuple[datetime, datetime] | None:
        """Return ``[start, end)`` of closed buckets to sync, or ``None``.

        ``end`` is ``now`` truncated to the bucket boundary, so only buckets
        that have fully closed are requested. When nothing is stored yet, the
        window is seeded with the configured backfill window.
        """
        engine = get_engine()
        if engine is None:
            return None
        duration = resolution_duration(timeframe)
        session = async_sessionmaker(bind=engine, expire_on_commit=False)()
        try:
            last_open = (
                await session.execute(
                    select(func.max(Candle.open_time))
                    .join(Market, Candle.market_id == Market.id)
                    .where(Market.symbol == symbol, Candle.timeframe == timeframe)
                )
            ).scalar()
        finally:
            await session.close()

        now = datetime.now(UTC)
        end = _truncate_to_bucket(now, duration)
        if last_open is None:
            start = _truncate_to_bucket(now - timedelta(days=self._backfill_days), duration)
        else:
            if last_open.tzinfo is None:
                last_open = last_open.replace(tzinfo=UTC)
            start = last_open + duration
        if start >= end:
            return None
        return start, end


def _truncate_to_bucket(value: datetime, duration: timedelta) -> datetime:
    """Floor ``value`` to the bucket grid of ``duration`` (e.g. 1h -> :00)."""
    seconds = int(duration.total_seconds())
    timestamp = int(value.timestamp())
    return datetime.fromtimestamp(timestamp - (timestamp % seconds), UTC)


async def run_sync_once(
    symbols: Sequence[str] | None = None,
    timeframes: Sequence[str] | None = None,
) -> SyncTickSummary:
    """Run one catch-up pass synchronously (CLI and manual verification)."""
    scheduler = CandleSyncScheduler(symbols=symbols, timeframes=timeframes)
    summary = await scheduler.run_catch_up()
    logger.info(
        "Candle sync run completed: synced=%d skipped=%d failed=%d in %.2fs",
        summary.synced,
        summary.skipped,
        summary.failed,
        summary.duration_seconds,
    )
    for report in summary.reports:
        logger.info(
            "Candle sync %s %s: inserted=%d duplicates_skipped=%d rejected=%d",
            report.symbol,
            report.timeframe,
            report.inserted,
            report.duplicates_skipped,
            report.rejected,
        )
    return summary
