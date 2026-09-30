"""Tests for `app.services.reddit_sync.RedditSyncScheduler` — mirrors
`tests/services/test_news_sync.py`'s own shape (window computation,
start/stop, the background loop), with the one thing this scheduler
needs proven that differs from News's own: `DISCOVERY_SAFETY_MARGIN`
here is a smaller, deliberately-scoped buffer (comments are queryable
promptly, unlike an article that can be discovered well after
publication — see this module's own docstring), not a bare floor.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.services.reddit_sync as reddit_sync_module
from app.connectors.reddit import REDDIT_VOLUME_SOURCE
from app.models.external_data import ConnectorSyncRun
from app.models.reddit import RedditComment
from app.services.reddit_ingest import RedditIngestError, RedditIngestReport
from app.services.reddit_sync import DISCOVERY_SAFETY_MARGIN, RedditSyncScheduler

FIXED_NOW = datetime(2026, 8, 20, 16, 33, 35, tzinfo=UTC)


class FakeDatetime(datetime):
    """datetime with a frozen ``now()`` for deterministic window tests."""

    @classmethod
    def now(cls, tz=None):  # noqa: D102
        return FIXED_NOW


async def seed_comment(
    session_factory: async_sessionmaker[AsyncSession], *, created_utc: datetime
) -> None:
    async with session_factory() as session:
        session.add(
            RedditComment(
                reddit_id=f"id-{created_utc.isoformat()}",
                subreddit="ethereum",
                author="someone",
                body="a comment",
                score=1,
                sentiment_score=0.1,
                created_utc=created_utc,
                permalink="/r/ethereum/comments/x/y/",
                raw_payload={},
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_start_noops_without_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a database the scheduler does not create a loop task."""
    monkeypatch.setattr(reddit_sync_module, "get_engine", lambda: None)
    scheduler = RedditSyncScheduler()
    await scheduler.start()
    assert not scheduler.running
    await scheduler.stop()


@pytest.mark.asyncio
async def test_window_backfills_when_nothing_stored(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing stored yet, the window seeds from the configured
    backfill window — `max_window_days` set wide enough here not to
    interfere, so this test stays purely about `backfill_days`; the
    clamp itself has its own dedicated tests below."""
    monkeypatch.setattr(reddit_sync_module, "get_engine", lambda: engine)

    scheduler = RedditSyncScheduler(backfill_days=7, max_window_days=10)
    window = await scheduler._catch_up_window(FIXED_NOW)
    assert window is not None
    start, end = window
    assert end == FIXED_NOW
    assert start == FIXED_NOW - timedelta(days=7)


@pytest.mark.asyncio
async def test_default_backfill_on_an_empty_table_is_two_days_not_3650(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real, deployed default: a fresh/empty table's first tick asks
    for 2 days, not the old 3650 — that used to hand one unattended tick
    10 years to page through, reliably tripping Arctic Shift's own
    sustained-request rate limit before even one subreddit's history was
    covered (see `reddit_sync_backfill_days`'s own comment in
    `app.core.config`)."""
    monkeypatch.setattr(reddit_sync_module, "get_engine", lambda: engine)

    scheduler = RedditSyncScheduler()
    window = await scheduler._catch_up_window(FIXED_NOW)
    assert window is not None
    start, end = window
    assert start == FIXED_NOW - timedelta(days=2)
    assert end == FIXED_NOW


@pytest.mark.asyncio
async def test_a_wide_gap_is_caught_up_over_several_ticks_not_one_burst(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 5-day gap (a scheduler restarted after days offline, not just an
    empty table) is not handed to one tick in full — `max_window_days`
    clamps the span, and the next tick resumes from wherever the first
    one's own real ingestion actually landed, continuing forward rather
    than either repeating the same window or jumping straight to now."""
    last = FIXED_NOW - timedelta(days=5)
    await seed_comment(session_factory, created_utc=last)
    monkeypatch.setattr(reddit_sync_module, "get_engine", lambda: engine)

    scheduler = RedditSyncScheduler(max_window_days=2)
    window = await scheduler._catch_up_window(FIXED_NOW)
    assert window is not None
    start, end = window
    assert start == last
    assert end == last + timedelta(days=2)
    assert end < FIXED_NOW  # the full 5-day gap was not covered in one tick

    # Simulate the first tick's real ingestion landing a comment right at
    # the clamped end — the next tick should resume from there.
    await seed_comment(session_factory, created_utc=end)
    window2 = await scheduler._catch_up_window(FIXED_NOW)
    assert window2 is not None
    start2, end2 = window2
    assert start2 == end
    assert end2 == min(FIXED_NOW, end + timedelta(days=2))


@pytest.mark.asyncio
async def test_window_resumes_from_the_last_stored_comment_when_recent(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the newest stored comment already predates
    `now - DISCOVERY_SAFETY_MARGIN` (the scheduler was stopped for a
    while), the window resumes from that comment's own `created_utc` —
    the margin only ever *widens* the window, never overrides a
    genuinely older last-known point with a narrower one."""
    last = FIXED_NOW - timedelta(days=3)
    await seed_comment(session_factory, created_utc=last)
    monkeypatch.setattr(reddit_sync_module, "get_engine", lambda: engine)

    # max_window_days set wide enough not to clamp — this test is purely
    # about `start` resuming from the last comment; the clamp itself has
    # its own dedicated tests above.
    scheduler = RedditSyncScheduler(max_window_days=10)
    window = await scheduler._catch_up_window(FIXED_NOW)
    assert window is not None
    start, end = window
    assert start == last
    assert end == FIXED_NOW


@pytest.mark.asyncio
async def test_window_never_narrower_than_the_discovery_safety_margin(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even though the newest stored comment is recent (well inside the
    safety margin), the window still reaches back the full
    `DISCOVERY_SAFETY_MARGIN`, never narrows to "nothing to re-check.\""""
    last = FIXED_NOW - timedelta(minutes=5)
    await seed_comment(session_factory, created_utc=last)
    monkeypatch.setattr(reddit_sync_module, "get_engine", lambda: engine)

    scheduler = RedditSyncScheduler()
    window = await scheduler._catch_up_window(FIXED_NOW)
    assert window is not None
    start, end = window
    assert start == FIXED_NOW - DISCOVERY_SAFETY_MARGIN
    assert start < last  # confirms the margin widened past the recent floor
    assert end == FIXED_NOW


@pytest.mark.asyncio
async def test_run_catch_up_calls_ingest_reddit_with_its_own_window(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[datetime, datetime]] = []

    async def fake_ingest_reddit(*, start: datetime, end: datetime) -> RedditIngestReport:
        calls.append((start, end))
        return RedditIngestReport(
            received=1,
            inserted=1,
            duplicates_skipped=0,
            rejected=0,
            days_recomputed=1,
            duration_seconds=0.01,
        )

    monkeypatch.setattr(reddit_sync_module, "get_engine", lambda: engine)
    monkeypatch.setattr(reddit_sync_module, "datetime", FakeDatetime)
    monkeypatch.setattr(reddit_sync_module, "ingest_reddit", fake_ingest_reddit)

    scheduler = RedditSyncScheduler()
    summary = await scheduler.run_catch_up()

    assert summary.attempted == 1
    assert summary.synced == 1
    assert summary.failed == 0
    assert len(calls) == 1
    start, end = calls[0]
    assert end == FIXED_NOW


@pytest.mark.asyncio
async def test_run_catch_up_isolates_a_failure(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_ingest_reddit(*, start: datetime, end: datetime) -> RedditIngestReport:
        raise RedditIngestError("boom")

    monkeypatch.setattr(reddit_sync_module, "get_engine", lambda: engine)
    monkeypatch.setattr(reddit_sync_module, "ingest_reddit", failing_ingest_reddit)

    scheduler = RedditSyncScheduler()
    summary = await scheduler.run_catch_up()

    assert summary.attempted == 1
    assert summary.synced == 0
    assert summary.failed == 1


@pytest.mark.asyncio
async def test_loop_runs_ticks_until_stopped(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The background loop starts, runs a tick, and stops cleanly."""
    calls: list[tuple[datetime, datetime]] = []

    async def fake_ingest_reddit(*, start: datetime, end: datetime) -> RedditIngestReport:
        calls.append((start, end))
        return RedditIngestReport(
            received=0,
            inserted=0,
            duplicates_skipped=0,
            rejected=0,
            days_recomputed=0,
            duration_seconds=0.01,
        )

    monkeypatch.setattr(reddit_sync_module, "get_engine", lambda: engine)
    monkeypatch.setattr(reddit_sync_module, "ingest_reddit", fake_ingest_reddit)

    scheduler = RedditSyncScheduler(interval_seconds=60)
    await scheduler.start()
    assert scheduler.running

    for _ in range(50):
        if calls:
            break
        await asyncio.sleep(0.02)
    assert calls, "first tick never ran"

    await scheduler.stop()
    assert not scheduler.running


async def _sync_runs(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[ConnectorSyncRun]:
    async with session_factory() as session:
        result = await session.execute(
            select(ConnectorSyncRun).where(ConnectorSyncRun.source == REDDIT_VOLUME_SOURCE)
        )
        return list(result.scalars())


@pytest.mark.asyncio
async def test_run_catch_up_records_a_successful_sync_run(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reddit runs on its own scheduler, not the generic one — its
    per-tick outcome must be recorded too, or connector health monitoring
    would silently skip it."""

    async def fake_ingest_reddit(*, start: datetime, end: datetime) -> RedditIngestReport:
        return RedditIngestReport(
            received=5,
            inserted=3,
            duplicates_skipped=1,
            rejected=1,
            days_recomputed=2,
            duration_seconds=0.5,
        )

    monkeypatch.setattr(reddit_sync_module, "get_engine", lambda: engine)
    monkeypatch.setattr(reddit_sync_module, "ingest_reddit", fake_ingest_reddit)

    await RedditSyncScheduler().run_catch_up()

    runs = await _sync_runs(session_factory)
    assert len(runs) == 1
    run = runs[0]
    assert run.success is True
    assert (run.received, run.inserted, run.duplicates_skipped, run.rejected) == (5, 3, 1, 1)
    assert run.duration_seconds == 0.5
    assert run.error_message is None


@pytest.mark.asyncio
async def test_run_catch_up_records_a_failed_sync_run(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_ingest_reddit(*, start: datetime, end: datetime) -> RedditIngestReport:
        raise RedditIngestError("boom")

    monkeypatch.setattr(reddit_sync_module, "get_engine", lambda: engine)
    monkeypatch.setattr(reddit_sync_module, "ingest_reddit", failing_ingest_reddit)

    await RedditSyncScheduler().run_catch_up()

    runs = await _sync_runs(session_factory)
    assert len(runs) == 1
    assert runs[0].success is False
    assert runs[0].error_message == "boom"
    assert runs[0].received == 0
