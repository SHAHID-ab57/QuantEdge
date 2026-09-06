"""Tests for the external data ingestion service
(``app.services.external_data_ingest``).

Mirrors ``tests/services/test_candle_ingest.py``'s own shape: a fake
connector stands in for the real network call — this module never talks to
alternative.me directly, that is ``tests/connectors/test_fear_greed.py``'s
job — while persistence is exercised against the real in-memory SQLite
session, exactly like the candle version.
"""

from datetime import UTC, datetime, timedelta
from typing import ClassVar
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import ConnectorMetadata, RawDataPoint
from app.connectors.errors import ConnectorNetworkError
from app.connectors.registry import ConnectorRegistry
from app.models.external_data import ExternalDataPoint
from app.repositories.external_data import ExternalDataRepository
from app.services import external_data_ingest
from app.services.external_data_ingest import (
    ExternalDataIngestError,
    _persist_points,
    ingest_external_data,
)
from tests.conftest import SessionFactory

BASE = datetime(2026, 1, 1, tzinfo=UTC)


class RevisableFakeConnector:
    """Same role as `FakeConnector`, but registered `revisable=True` — a
    stand-in for `app.connectors.defillama.DefiLlamaConnector` without any
    real network call, for `TestRevisableIngestion` below."""

    metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        source="fake_revisable_source",
        label="Fake Revisable",
        description="A test double for a revisable source.",
        revisable=True,
    )

    points: tuple[RawDataPoint, ...] = ()
    calls: int = 0

    async def fetch(self, start: datetime, end: datetime) -> tuple[RawDataPoint, ...]:
        RevisableFakeConnector.calls += 1
        return RevisableFakeConnector.points


class FakeConnector:
    """A controllable stand-in for a real `Connector` — returns whatever
    `points` were configured, or raises `error` if one was set. Class-level
    state (reset by the `reset_fake_connector` fixture below) since the
    registry builds a fresh instance per `get()` call, mirroring the real
    contract."""

    #: `ClassVar`-annotated so `type[FakeConnector]` satisfies the
    #: `Connector` protocol's own `metadata: ClassVar[...]` — see
    #: `app.connectors.fear_greed.FearGreedConnector`'s own `metadata`.
    metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        source="fake_source", label="Fake", description="A test double."
    )

    points: tuple[RawDataPoint, ...] = ()
    error: Exception | None = None
    calls: int = 0

    async def fetch(self, start: datetime, end: datetime) -> tuple[RawDataPoint, ...]:
        FakeConnector.calls += 1
        if FakeConnector.error is not None:
            raise FakeConnector.error
        return FakeConnector.points


@pytest.fixture(autouse=True)
def reset_fake_connector():
    FakeConnector.points = ()
    FakeConnector.error = None
    FakeConnector.calls = 0
    RevisableFakeConnector.points = ()
    RevisableFakeConnector.calls = 0
    yield


@pytest.fixture
def revisable_fake_registry(monkeypatch: pytest.MonkeyPatch) -> ConnectorRegistry:
    """An isolated registry holding only `RevisableFakeConnector` — kept
    separate from `fake_registry` so a `revisable=True` source is never
    accidentally exercised by `TestIngestExternalData`'s own tests."""
    registry = ConnectorRegistry()
    registry.register(RevisableFakeConnector)
    monkeypatch.setattr(external_data_ingest, "default_connector_registry", registry)
    monkeypatch.setattr(external_data_ingest, "load_builtin_connectors", lambda: None)
    return registry


@pytest.fixture
def fake_registry(monkeypatch: pytest.MonkeyPatch) -> ConnectorRegistry:
    """An isolated registry holding only `FakeConnector`, wired in place of
    the real `default_registry` — the same isolation
    `tests/connectors/test_registry.py` uses for its own non-discovery
    tests, applied here so this module never depends on (or accidentally
    exercises) the real Fear & Greed connector."""
    registry = ConnectorRegistry()
    registry.register(FakeConnector)
    monkeypatch.setattr(external_data_ingest, "default_connector_registry", registry)
    monkeypatch.setattr(external_data_ingest, "load_builtin_connectors", lambda: None)
    return registry


async def count_points(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(ExternalDataPoint))).scalar_one()


@pytest.mark.asyncio
class TestIngestExternalData:
    async def test_fetches_and_persists_every_point(
        self, fake_registry: ConnectorRegistry, session_factory: SessionFactory
    ) -> None:
        FakeConnector.points = (
            RawDataPoint(timestamp=BASE, value=30.0, raw_payload={"value": "30"}),
            RawDataPoint(
                timestamp=BASE + timedelta(days=1), value=70.0, raw_payload={"value": "70"}
            ),
        )
        report = await ingest_external_data(
            source="fake_source",
            start=BASE,
            end=BASE + timedelta(days=1),
            session=session_factory(),
        )

        assert report.source == "fake_source"
        assert report.received == 2
        assert report.inserted == 2
        assert report.duplicates_skipped == 0
        assert report.rejected == 0

        async with session_factory() as session:
            assert await count_points(session) == 2

    async def test_duplicate_points_are_skipped_idempotently(
        self, fake_registry: ConnectorRegistry, session_factory: SessionFactory
    ) -> None:
        """Re-ingesting the same range inserts nothing the second time —
        the application-layer check `app.models.external_data
        .ExternalDataPoint`'s own docstring calls for, since the unique
        constraint alone cannot be relied on with a `NULL` symbol."""
        FakeConnector.points = (RawDataPoint(timestamp=BASE, value=30.0),)

        first = await ingest_external_data(
            source="fake_source", start=BASE, end=BASE, session=session_factory()
        )
        second = await ingest_external_data(
            source="fake_source", start=BASE, end=BASE, session=session_factory()
        )

        assert first.inserted == 1
        assert first.duplicates_skipped == 0
        assert second.inserted == 0
        assert second.duplicates_skipped == 1

        async with session_factory() as session:
            assert await count_points(session) == 1

    async def test_network_failure_propagates_and_persists_nothing(
        self, fake_registry: ConnectorRegistry, session_factory: SessionFactory
    ) -> None:
        FakeConnector.error = ConnectorNetworkError("network down")

        with pytest.raises(ConnectorNetworkError):
            await ingest_external_data(
                source="fake_source", start=BASE, end=BASE, session=session_factory()
            )

        async with session_factory() as session:
            assert await count_points(session) == 0

    async def test_unknown_source_raises_before_any_fetch(
        self, fake_registry: ConnectorRegistry, session_factory: SessionFactory
    ) -> None:
        with pytest.raises(ExternalDataIngestError, match="does_not_exist"):
            await ingest_external_data(
                source="does_not_exist", start=BASE, end=BASE, session=session_factory()
            )
        assert FakeConnector.calls == 0

    async def test_naive_datetimes_are_rejected_before_any_fetch(
        self, fake_registry: ConnectorRegistry, session_factory: SessionFactory
    ) -> None:
        with pytest.raises(ExternalDataIngestError, match="timezone-aware"):
            await ingest_external_data(
                source="fake_source",
                start=BASE.replace(tzinfo=None),
                end=BASE,
                session=session_factory(),
            )
        assert FakeConnector.calls == 0

    async def test_end_before_start_is_rejected(
        self, fake_registry: ConnectorRegistry, session_factory: SessionFactory
    ) -> None:
        with pytest.raises(ExternalDataIngestError, match="end must not be before start"):
            await ingest_external_data(
                source="fake_source",
                start=BASE,
                end=BASE - timedelta(days=1),
                session=session_factory(),
            )
        assert FakeConnector.calls == 0


@pytest.mark.asyncio
class TestRevisableIngestion:
    """`ConnectorMetadata.revisable=True`'s own ingestion-layer behavior —
    `app.connectors.defillama`'s reason for existing. Kept separate from
    `TestIngestExternalData` above: every one of those tests uses the
    ordinary `revisable=False` `FakeConnector` and must stay byte-for-byte
    unaffected by this feature existing at all (each one already passed
    before this class was added — see the full suite run, not just this
    file, for that regression proof)."""

    async def test_a_non_revisable_source_still_skips_a_changed_value_unconditionally(
        self, fake_registry: ConnectorRegistry, session_factory: SessionFactory
    ) -> None:
        """The critical regression proof: `revisable=False` (every
        connector before DefiLlama) must keep skipping a timestamp
        collision even when the newly-fetched value genuinely differs —
        exactly today's existing behavior, untouched by this feature."""
        FakeConnector.points = (RawDataPoint(timestamp=BASE, value=30.0),)
        first = await ingest_external_data(
            source="fake_source", start=BASE, end=BASE, session=session_factory()
        )
        assert first.inserted == 1
        assert first.updated == 0

        FakeConnector.points = (RawDataPoint(timestamp=BASE, value=99.0),)
        second = await ingest_external_data(
            source="fake_source", start=BASE, end=BASE, session=session_factory()
        )
        assert second.inserted == 0
        assert second.updated == 0
        assert second.duplicates_skipped == 1

        async with session_factory() as session:
            stored = (await session.execute(select(ExternalDataPoint.value))).scalar_one()
        assert stored == 30.0  # the original value, never overwritten

    async def test_a_revisable_source_overwrites_a_changed_value(
        self, revisable_fake_registry: ConnectorRegistry, session_factory: SessionFactory
    ) -> None:
        RevisableFakeConnector.points = (RawDataPoint(timestamp=BASE, value=40.0),)
        first = await ingest_external_data(
            source="fake_revisable_source", start=BASE, end=BASE, session=session_factory()
        )
        assert first.inserted == 1
        assert first.updated == 0
        assert first.duplicates_skipped == 0

        RevisableFakeConnector.points = (RawDataPoint(timestamp=BASE, value=41.0),)
        second = await ingest_external_data(
            source="fake_revisable_source", start=BASE, end=BASE, session=session_factory()
        )
        assert second.inserted == 0
        assert second.updated == 1
        assert second.duplicates_skipped == 0

        async with session_factory() as session:
            stored = (await session.execute(select(ExternalDataPoint.value))).scalar_one()
        assert stored == 41.0  # overwritten in place

    async def test_a_revisable_source_still_skips_an_unchanged_re_fetch(
        self, revisable_fake_registry: ConnectorRegistry, session_factory: SessionFactory
    ) -> None:
        """Revisable does not mean "always rewrite" — an unchanged
        re-fetch is still just a duplicate skip, never a wasted write."""
        RevisableFakeConnector.points = (RawDataPoint(timestamp=BASE, value=40.0),)
        await ingest_external_data(
            source="fake_revisable_source", start=BASE, end=BASE, session=session_factory()
        )

        second = await ingest_external_data(
            source="fake_revisable_source", start=BASE, end=BASE, session=session_factory()
        )
        assert second.inserted == 0
        assert second.updated == 0
        assert second.duplicates_skipped == 1

    async def test_a_revisable_source_only_overwrites_the_point_that_actually_changed(
        self, revisable_fake_registry: ConnectorRegistry, session_factory: SessionFactory
    ) -> None:
        """A batch mixing an unchanged point and a genuinely revised one
        must resolve each independently — never an all-or-nothing rewrite
        of the whole batch."""
        RevisableFakeConnector.points = (
            RawDataPoint(timestamp=BASE, value=40.0),
            RawDataPoint(timestamp=BASE + timedelta(days=1), value=50.0),
        )
        await ingest_external_data(
            source="fake_revisable_source",
            start=BASE,
            end=BASE + timedelta(days=1),
            session=session_factory(),
        )

        RevisableFakeConnector.points = (
            RawDataPoint(timestamp=BASE, value=40.0),  # unchanged
            RawDataPoint(timestamp=BASE + timedelta(days=1), value=51.0),  # revised
        )
        second = await ingest_external_data(
            source="fake_revisable_source",
            start=BASE,
            end=BASE + timedelta(days=1),
            session=session_factory(),
        )
        assert second.updated == 1
        assert second.duplicates_skipped == 1

        async with session_factory() as session:
            # `.replace(tzinfo=UTC)` works around SQLite's own naive
            # datetime round-trip quirk (`ExternalDataRepository`'s own
            # `_as_utc` docstring has the full account) — this test reads
            # the raw column directly rather than through a repository
            # method that already normalizes it.
            values = {
                row[0].replace(tzinfo=UTC): row[1]
                for row in (
                    await session.execute(
                        select(ExternalDataPoint.timestamp, ExternalDataPoint.value)
                    )
                ).all()
            }
        assert values[BASE] == 40.0
        assert values[BASE + timedelta(days=1)] == 51.0


@pytest.mark.asyncio
async def test_database_conflict_is_isolated_and_rejected(
    session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The database-level backstop, forced past the application-layer
    pre-check exactly like `test_candle_ingest.py`'s own
    `test_database_conflict_is_isolated_and_rejected` does — proving the
    per-row savepoint isolation is real, executed code, not merely the
    (normal, expected) application-layer skip.

    Deliberately uses a non-`None` `symbol`: with Fear & Greed's own
    `symbol=None`, Postgres/SQLite both treat two `NULL`s as distinct for
    uniqueness, so *this specific* backstop can never actually fire for
    `fear_greed` — see `ExternalDataPoint`'s own docstring. This proves the
    backstop is real for a future connector that reports a genuine
    per-symbol value, and documents that Fear & Greed itself relies on the
    application-layer check alone, with no database-level second line of
    defense — a known, accepted limitation, not an oversight.
    """
    existing_time = BASE + timedelta(days=1)
    async with session_factory() as session:
        session.add(
            ExternalDataPoint(
                source="fake_source", symbol="BTC", timestamp=existing_time, value=1.0
            )
        )
        await session.commit()

    # Simulate a race: the application-layer pre-check reports "nothing
    # exists yet" even though the row above was already committed.
    monkeypatch.setattr(
        ExternalDataRepository, "list_existing_timestamps", AsyncMock(return_value=set())
    )

    async with session_factory() as session:
        inserted, updated, duplicates_skipped, rejected = await _persist_points(
            session,
            "fake_source",
            [RawDataPoint(timestamp=existing_time, value=9.0, symbol="BTC")],
        )

    assert inserted == 0
    assert updated == 0
    assert duplicates_skipped == 0
    assert rejected == 1

    async with session_factory() as session:
        assert await count_points(session) == 1
