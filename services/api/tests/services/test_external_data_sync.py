"""Tests for the periodic external data catch-up synchronization service.

Mirrors ``tests/services/test_candle_sync.py``'s own shape: the scheduler's
database reads run against a real in-memory SQLite engine; ingestion itself
is faked so these tests focus on window computation, source resolution,
skipping, and failure isolation — the real ingestion path is covered by
``tests/services/test_external_data_ingest.py``.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.external_data import ExternalDataPoint
from app.services import external_data_sync
from app.services.external_data_ingest import ExternalDataIngestReport
from app.services.external_data_sync import ExternalDataSyncScheduler

FIXED_NOW = datetime(2026, 8, 20, 16, 33, 35, tzinfo=UTC)


class FakeDatetime(datetime):
    """datetime with a frozen ``now()`` for deterministic window tests."""

    @classmethod
    def now(cls, tz=None):  # noqa: D102
        return FIXED_NOW


def fake_ingest(*, failure_source: str | None = None):
    """Build an `ingest_external_data` fake that records calls."""
    calls: list[tuple[str, datetime, datetime]] = []

    async def ingest(*, source: str, start: datetime, end: datetime) -> ExternalDataIngestReport:
        calls.append((source, start, end))
        if failure_source is not None and source == failure_source:
            raise RuntimeError("boom")
        return ExternalDataIngestReport(
            source=source,
            start=start,
            end=end,
            received=1,
            inserted=1,
            updated=0,
            duplicates_skipped=0,
            rejected=0,
            duration_seconds=0.01,
        )

    return ingest, calls


async def _fixed_window(source: str, now: datetime) -> tuple[datetime, datetime]:
    """A stand-in for `_catch_up_window` — must be a coroutine function
    (like the real method) since callers `await` it; a plain lambda
    returning a tuple directly breaks that `await`."""
    return now - timedelta(days=1), now


async def seed_point(
    session_factory: async_sessionmaker[AsyncSession],
    source: str,
    *,
    timestamp: datetime,
) -> None:
    """Insert one point for the source."""
    async with session_factory() as session:
        session.add(ExternalDataPoint(source=source, symbol=None, timestamp=timestamp, value=1.0))
        await session.commit()


@pytest.mark.asyncio
async def test_start_noops_without_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a database the scheduler does not create a loop task."""
    monkeypatch.setattr(external_data_sync, "get_engine", lambda: None)
    scheduler = ExternalDataSyncScheduler(sources=["fear_greed"])
    await scheduler.start()
    assert not scheduler.running
    await scheduler.stop()


@pytest.mark.asyncio
async def test_window_backfills_when_nothing_stored(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source with no stored points seeds from the configured backfill window."""
    monkeypatch.setattr(external_data_sync, "get_engine", lambda: engine)

    scheduler = ExternalDataSyncScheduler(sources=["fear_greed"], backfill_days=7)
    window = await scheduler._catch_up_window("fear_greed", FIXED_NOW)
    assert window is not None
    start, end = window
    assert end == FIXED_NOW
    assert start == FIXED_NOW - timedelta(days=7)


@pytest.mark.asyncio
async def test_window_resumes_from_the_last_stored_point(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The window resumes *at* (not after) the newest stored point — this
    table's own inclusive-both-ends convention (unlike `Candle`'s half-open
    buckets) means the last point is safely re-fetched and skipped as a
    duplicate rather than risking a gap."""
    last = FIXED_NOW - timedelta(days=2)
    await seed_point(session_factory, "fear_greed", timestamp=last)
    monkeypatch.setattr(external_data_sync, "get_engine", lambda: engine)

    scheduler = ExternalDataSyncScheduler(sources=["fear_greed"])
    window = await scheduler._catch_up_window("fear_greed", FIXED_NOW)
    assert window is not None
    start, end = window
    assert start == last
    assert end == FIXED_NOW


@pytest.mark.asyncio
async def test_window_is_none_when_already_current(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source whose newest point is already at (or past) `now` is skipped."""
    await seed_point(session_factory, "fear_greed", timestamp=FIXED_NOW)
    monkeypatch.setattr(external_data_sync, "get_engine", lambda: engine)

    scheduler = ExternalDataSyncScheduler(sources=["fear_greed"])
    assert await scheduler._catch_up_window("fear_greed", FIXED_NOW) is None


@pytest.mark.asyncio
async def test_run_catch_up_syncs_every_configured_source(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every configured, registered source is ingested with its own window."""
    monkeypatch.setattr(external_data_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(external_data_sync, "load_builtin_connectors", lambda: None)
    monkeypatch.setattr(external_data_sync.default_connector_registry, "has", lambda source: True)
    ingest, calls = fake_ingest()
    monkeypatch.setattr(external_data_sync, "ingest_external_data", ingest)

    scheduler = ExternalDataSyncScheduler(sources=["fear_greed", "another_source"])
    monkeypatch.setattr(scheduler, "_catch_up_window", _fixed_window)
    monkeypatch.setattr(external_data_sync, "datetime", FakeDatetime)

    summary = await scheduler.run_catch_up()

    assert summary.attempted == 2
    assert summary.synced == 2
    assert summary.failed == 0
    sources = {call[0] for call in calls}
    assert sources == {"fear_greed", "another_source"}
    for _, start, end in calls:
        assert start < end
        assert end == FIXED_NOW


@pytest.mark.asyncio
async def test_run_catch_up_skips_unknown_sources(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured source with no registered connector is excluded, not
    ingested and not a failure."""
    monkeypatch.setattr(external_data_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(external_data_sync, "load_builtin_connectors", lambda: None)
    monkeypatch.setattr(
        external_data_sync.default_connector_registry,
        "has",
        lambda source: source == "fear_greed",
    )
    ingest, calls = fake_ingest()
    monkeypatch.setattr(external_data_sync, "ingest_external_data", ingest)

    scheduler = ExternalDataSyncScheduler(sources=["fear_greed", "does_not_exist"])
    monkeypatch.setattr(scheduler, "_catch_up_window", _fixed_window)
    monkeypatch.setattr(external_data_sync, "datetime", FakeDatetime)

    summary = await scheduler.run_catch_up()

    assert summary.attempted == 1
    assert [call[0] for call in calls] == ["fear_greed"]


@pytest.mark.asyncio
async def test_run_catch_up_isolates_failures(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One failing source does not stop the remaining sources."""
    monkeypatch.setattr(external_data_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(external_data_sync, "load_builtin_connectors", lambda: None)
    monkeypatch.setattr(external_data_sync.default_connector_registry, "has", lambda source: True)
    ingest, calls = fake_ingest(failure_source="fear_greed")
    monkeypatch.setattr(external_data_sync, "ingest_external_data", ingest)

    scheduler = ExternalDataSyncScheduler(sources=["fear_greed", "another_source"])
    monkeypatch.setattr(scheduler, "_catch_up_window", _fixed_window)
    monkeypatch.setattr(external_data_sync, "datetime", FakeDatetime)

    summary = await scheduler.run_catch_up()

    assert summary.failed == 1
    assert summary.synced == 1
    assert {call[0] for call in calls} == {"fear_greed", "another_source"}


@pytest.mark.asyncio
async def test_run_catch_up_skips_already_current_sources(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source already current is counted as attempted but never ingested."""
    await seed_point(session_factory, "fear_greed", timestamp=FIXED_NOW)
    monkeypatch.setattr(external_data_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(external_data_sync, "load_builtin_connectors", lambda: None)
    monkeypatch.setattr(external_data_sync.default_connector_registry, "has", lambda source: True)
    monkeypatch.setattr(external_data_sync, "datetime", FakeDatetime)
    ingest, calls = fake_ingest()
    monkeypatch.setattr(external_data_sync, "ingest_external_data", ingest)

    scheduler = ExternalDataSyncScheduler(sources=["fear_greed"])
    summary = await scheduler.run_catch_up()

    assert summary.attempted == 1
    assert summary.synced == 0
    assert calls == []


@pytest.mark.asyncio
async def test_loop_runs_ticks_until_stopped(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The background loop starts, runs a tick, and stops cleanly."""
    monkeypatch.setattr(external_data_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(external_data_sync, "load_builtin_connectors", lambda: None)
    monkeypatch.setattr(external_data_sync.default_connector_registry, "has", lambda source: True)
    monkeypatch.setattr(external_data_sync, "datetime", FakeDatetime)
    ingest, calls = fake_ingest()
    monkeypatch.setattr(external_data_sync, "ingest_external_data", ingest)

    scheduler = ExternalDataSyncScheduler(sources=["fear_greed"], interval_seconds=60)
    monkeypatch.setattr(scheduler, "_catch_up_window", _fixed_window)
    await scheduler.start()
    assert scheduler.running

    for _ in range(50):
        if calls:
            break
        await asyncio.sleep(0.02)
    assert calls, "first tick never ran"

    await scheduler.stop()
    assert not scheduler.running
    assert [call[0] for call in calls] == ["fear_greed"]


@pytest.mark.asyncio
async def test_empty_source_list_is_a_clean_noop(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No configured and no registered sources produces an empty, successful
    summary — never an error."""
    monkeypatch.setattr(external_data_sync, "get_engine", lambda: engine)
    monkeypatch.setattr(external_data_sync, "load_builtin_connectors", lambda: None)
    monkeypatch.setattr(external_data_sync.default_connector_registry, "names", lambda: ())

    scheduler = ExternalDataSyncScheduler(sources=[])
    summary = await scheduler.run_catch_up()

    assert summary.attempted == 0
    assert summary.synced == 0
    assert summary.failed == 0
