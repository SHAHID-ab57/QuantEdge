"""Tests for `app.services.news_sync.NewsSyncScheduler` — mirrors
`tests/services/test_external_data_sync.py`'s own shape (window
computation, start/stop, the background loop), with the one genuinely
new thing this scheduler needs proven: `DISCOVERY_SAFETY_MARGIN` actually
widens the window rather than pinning `start` to the bare newest-stored
floor (see that module's own docstring for why a bare floor is the wrong
choice here).
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.services.news_sync as news_sync_module
from app.models.news import NewsArticle
from app.services.news_ingest import NewsIngestError, NewsIngestReport
from app.services.news_sync import DISCOVERY_SAFETY_MARGIN, NewsSyncScheduler

FIXED_NOW = datetime(2026, 8, 20, 16, 33, 35, tzinfo=UTC)


class FakeDatetime(datetime):
    """datetime with a frozen ``now()`` for deterministic window tests."""

    @classmethod
    def now(cls, tz=None):  # noqa: D102
        return FIXED_NOW


async def seed_article(
    session_factory: async_sessionmaker[AsyncSession], *, published_at: datetime
) -> None:
    async with session_factory() as session:
        session.add(
            NewsArticle(
                marketaux_uuid=f"uuid-{published_at.isoformat()}",
                headline="Headline",
                source="example.com",
                url="https://example.com/a",
                published_at=published_at,
                sentiment_score=0.1,
                primary_symbol="ETHUSD",
                symbols=["ETHUSD"],
                raw_payload={},
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_start_noops_without_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a database the scheduler does not create a loop task."""
    monkeypatch.setattr(news_sync_module, "get_engine", lambda: None)
    scheduler = NewsSyncScheduler()
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
    backfill window — identical to `ExternalDataSyncScheduler`'s own
    "nothing stored" case."""
    monkeypatch.setattr(news_sync_module, "get_engine", lambda: engine)

    scheduler = NewsSyncScheduler(backfill_days=7)
    window = await scheduler._catch_up_window(FIXED_NOW)
    assert window is not None
    start, end = window
    assert end == FIXED_NOW
    assert start == FIXED_NOW - timedelta(days=7)


@pytest.mark.asyncio
async def test_window_resumes_from_the_last_stored_article_when_recent(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the newest stored article already predates
    `now - DISCOVERY_SAFETY_MARGIN` (a real gap wider than the margin
    alone — e.g. the scheduler was stopped for a while), the window
    resumes from that article's own `published_at`, not just the margin
    — the margin only ever *widens* the window, it never overrides a
    genuinely older last-known point with a narrower one."""
    last = FIXED_NOW - timedelta(days=30)
    await seed_article(session_factory, published_at=last)
    monkeypatch.setattr(news_sync_module, "get_engine", lambda: engine)

    scheduler = NewsSyncScheduler()
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
    """The load-bearing proof of this scheduler's own real difference
    from `ExternalDataSyncScheduler`: even though the newest stored
    article is *recent* (well inside the safety margin — we look
    "already caught up" by a bare-floor standard), the window still
    reaches back the *full* `DISCOVERY_SAFETY_MARGIN`, not just to that
    recent article — never narrows to "nothing to re-check" the way a
    bare floor would, since a late-discovered article for the
    in-between period could otherwise be missed forever."""
    last = FIXED_NOW - timedelta(hours=1)
    await seed_article(session_factory, published_at=last)
    monkeypatch.setattr(news_sync_module, "get_engine", lambda: engine)

    scheduler = NewsSyncScheduler()
    window = await scheduler._catch_up_window(FIXED_NOW)
    assert window is not None
    start, end = window
    assert start == FIXED_NOW - DISCOVERY_SAFETY_MARGIN
    assert start < last  # confirms the margin widened past the recent floor
    assert end == FIXED_NOW


@pytest.mark.asyncio
async def test_run_catch_up_calls_ingest_news_with_its_own_window(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[datetime, datetime]] = []

    async def fake_ingest_news(*, start: datetime, end: datetime) -> NewsIngestReport:
        calls.append((start, end))
        return NewsIngestReport(
            received=1,
            inserted=1,
            duplicates_skipped=0,
            rejected=0,
            days_recomputed=1,
            duration_seconds=0.01,
        )

    monkeypatch.setattr(news_sync_module, "get_engine", lambda: engine)
    monkeypatch.setattr(news_sync_module, "datetime", FakeDatetime)
    monkeypatch.setattr(news_sync_module, "ingest_news", fake_ingest_news)

    scheduler = NewsSyncScheduler()
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
    async def failing_ingest_news(*, start: datetime, end: datetime) -> NewsIngestReport:
        raise NewsIngestError("boom")

    monkeypatch.setattr(news_sync_module, "get_engine", lambda: engine)
    monkeypatch.setattr(news_sync_module, "ingest_news", failing_ingest_news)

    scheduler = NewsSyncScheduler()
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

    async def fake_ingest_news(*, start: datetime, end: datetime) -> NewsIngestReport:
        calls.append((start, end))
        return NewsIngestReport(
            received=0,
            inserted=0,
            duplicates_skipped=0,
            rejected=0,
            days_recomputed=0,
            duration_seconds=0.01,
        )

    monkeypatch.setattr(news_sync_module, "get_engine", lambda: engine)
    monkeypatch.setattr(news_sync_module, "ingest_news", fake_ingest_news)

    scheduler = NewsSyncScheduler(interval_seconds=60)
    await scheduler.start()
    assert scheduler.running

    for _ in range(50):
        if calls:
            break
        await asyncio.sleep(0.02)
    assert calls, "first tick never ran"

    await scheduler.stop()
    assert not scheduler.running
