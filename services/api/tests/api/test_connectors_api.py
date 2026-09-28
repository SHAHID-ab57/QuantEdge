"""External Data Connectors read API tests (M4-E1-T3's own backend) —
mirrors ``tests/api/test_features_api.py``'s own shape: a real FastAPI
app over ASGI with the in-memory SQLite database, so routing, JSON
serialization, and the shared ``AppError`` -> JSON envelope are all
covered end to end.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

import app.services.connectors as connectors_service_module
from app.connectors.registry import ConnectorRegistry
from app.models.external_data import ConnectorSyncRun, ExternalDataPoint
from tests.conftest import SessionFactory


async def seed_point(
    session_factory: SessionFactory,
    *,
    source: str = "fear_greed",
    value: float,
    timestamp: datetime,
) -> None:
    """Insert one real external data point directly."""
    async with session_factory() as session:
        session.add(ExternalDataPoint(source=source, symbol=None, timestamp=timestamp, value=value))
        await session.commit()


async def seed_runs(
    session_factory: SessionFactory,
    outcomes: list[bool],
    *,
    source: str = "fear_greed",
) -> None:
    """Insert sync runs for a source, `outcomes` given newest first."""
    now = datetime.now(UTC)
    async with session_factory() as session:
        for minutes_ago, success in enumerate(outcomes):
            started = now - timedelta(minutes=minutes_ago)
            session.add(
                ConnectorSyncRun(
                    source=source,
                    started_at=started,
                    completed_at=started,
                    success=success,
                    received=1 if success else 0,
                    inserted=0,
                    error_message=None if success else "upstream 503",
                )
            )
        await session.commit()


async def fear_greed_status(client: httpx.AsyncClient) -> str:
    body = (await client.get("/api/v1/connectors")).json()
    return next(e for e in body["connectors"] if e["source"] == "fear_greed")["health_status"]


class TestConnectorCatalogueEndpoint:
    async def test_lists_the_registered_connector(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/connectors")
        assert response.status_code == 200
        body = response.json()
        sources = {entry["source"] for entry in body["connectors"]}
        assert "fear_greed" in sources
        assert body["total"] == len(body["connectors"])

    async def test_a_newly_registered_connector_appears_with_zero_code_change(
        self, client: httpx.AsyncClient
    ) -> None:
        """The Data Sources page's own registry-driven guarantee: `fed_funds_rate`
        (`app/connectors/fred.py`) was added well after this endpoint/page was
        first built, and appears here with no change to either — the same
        proof `test_features_api.py` already gives `/features`."""
        body = (await client.get("/api/v1/connectors")).json()
        sources = {entry["source"] for entry in body["connectors"]}
        assert "fed_funds_rate" in sources
        fed_funds = next(e for e in body["connectors"] if e["source"] == "fed_funds_rate")
        assert fed_funds["label"] == "Federal Funds Rate"
        assert fed_funds["requires_auth"] is True

        # A third connector, added later still — same guarantee again.
        assert "eth_gas_price" in sources
        gas_price = next(e for e in body["connectors"] if e["source"] == "eth_gas_price")
        assert gas_price["label"] == "Ethereum Gas Price"
        assert gas_price["requires_auth"] is True

        # A fourth connector — the first requiring no authentication since
        # Fear & Greed itself.
        assert "eth_tvl" in sources
        eth_tvl = next(e for e in body["connectors"] if e["source"] == "eth_tvl")
        assert eth_tvl["label"] == "Ethereum Chain TVL"
        assert eth_tvl["requires_auth"] is False

        # A fifth connector, added later still — same guarantee again.
        assert "btc_dominance" in sources
        btc_dominance = next(e for e in body["connectors"] if e["source"] == "btc_dominance")
        assert btc_dominance["label"] == "Bitcoin Dominance"
        assert btc_dominance["requires_auth"] is False

        # A sixth connector — the first whose own ingestion is handled by
        # a dedicated pipeline (auto_synced=False), not the generic
        # scheduler; this catalogue endpoint doesn't know or care.
        assert "news_sentiment" in sources
        news_sentiment = next(e for e in body["connectors"] if e["source"] == "news_sentiment")
        assert news_sentiment["label"] == "Marketaux News Sentiment"
        assert news_sentiment["requires_auth"] is True

    async def test_reports_null_latest_value_before_anything_is_ingested(
        self, client: httpx.AsyncClient
    ) -> None:
        """A registered connector with zero stored points reports nulls,
        never a crash or a fabricated value."""
        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["latest_value"] is None
        assert entry["latest_timestamp"] is None
        assert entry["label"] == "Fear & Greed Index"
        assert entry["requires_auth"] is False
        assert entry["health_status"] == "never_ingested"

    async def test_reports_the_real_latest_value_once_ingested(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_point(session_factory, value=30.0, timestamp=datetime(2026, 1, 1, tzinfo=UTC))
        await seed_point(session_factory, value=70.0, timestamp=datetime(2026, 1, 2, tzinfo=UTC))

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["latest_value"] == 70.0
        assert entry["latest_timestamp"] == "2026-01-02T00:00:00Z"

    async def test_reports_healthy_for_a_point_within_the_expected_cadence(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        """Fear & Greed's own real expected_interval_seconds is 86400s (1
        day) — a point from an hour ago is well within that."""
        await seed_point(
            session_factory, value=42.0, timestamp=datetime.now(UTC) - timedelta(hours=1)
        )

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["health_status"] == "healthy"

    async def test_reports_stale_for_a_point_well_past_the_expected_cadence(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        """A point 30 days old is far past Fear & Greed's own 3-day
        (STALE_MULTIPLIER x 1 day) staleness threshold."""
        await seed_point(
            session_factory, value=42.0, timestamp=datetime.now(UTC) - timedelta(days=30)
        )

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["health_status"] == "stale"

    async def test_reports_failing_when_recent_syncs_all_failed_despite_fresh_data(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        """The gap this closes: a connector erroring on every tick used to
        read `healthy` until its staleness threshold independently elapsed,
        because its last good point was still recent."""
        await seed_point(
            session_factory, value=42.0, timestamp=datetime.now(UTC) - timedelta(hours=1)
        )
        assert await fear_greed_status(client) == "healthy"

        await seed_runs(session_factory, [False, False, False])

        assert await fear_greed_status(client) == "failing"

    async def test_two_failed_syncs_are_not_yet_failing(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_point(
            session_factory, value=42.0, timestamp=datetime.now(UTC) - timedelta(hours=1)
        )
        await seed_runs(session_factory, [False, False])

        assert await fear_greed_status(client) == "healthy"

    async def test_a_recent_success_after_failures_clears_failing(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        """Newest first: the connector recovered on its latest attempt."""
        await seed_point(
            session_factory, value=42.0, timestamp=datetime.now(UTC) - timedelta(hours=1)
        )
        await seed_runs(session_factory, [True, False, False, False, False])

        assert await fear_greed_status(client) == "healthy"

    async def test_failing_takes_precedence_over_never_ingested(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_runs(session_factory, [False, False, False])

        assert await fear_greed_status(client) == "failing"

    async def test_failures_for_one_source_do_not_affect_another(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_point(
            session_factory, value=42.0, timestamp=datetime.now(UTC) - timedelta(hours=1)
        )
        await seed_runs(session_factory, [False, False, False], source="eth_tvl")

        assert await fear_greed_status(client) == "healthy"

    async def test_zero_registered_connectors_is_handled_not_crashed_on(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Shouldn't happen post-M4-E1-T1, but the endpoint must still
        return a clean, empty catalogue rather than an error."""
        monkeypatch.setattr(
            connectors_service_module, "default_connector_registry", ConnectorRegistry()
        )
        monkeypatch.setattr(connectors_service_module, "load_builtin_connectors", lambda: None)

        response = await client.get("/api/v1/connectors")
        assert response.status_code == 200
        body = response.json()
        assert body["connectors"] == []
        assert body["total"] == 0

    async def test_is_mounted_unversioned_too(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/connectors")).status_code == 200


class TestSyncTimingFields:
    """`total_points`/`expected_interval_seconds`/`last_attempt_at`/
    `last_attempt_success`/`next_sync_at` — added so the Data Sources page can
    explain *why* a connector is stale (an overdue scheduler tick) instead of
    only naming the fact, and so a value's own precision is never confused
    with how long ago it was fetched."""

    async def test_total_points_counts_every_stored_row_for_that_source_only(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        for day in range(3):
            await seed_point(
                session_factory, value=float(day), timestamp=datetime(2026, 1, 1 + day, tzinfo=UTC)
            )
        await seed_point(
            session_factory, value=1.0, timestamp=datetime(2026, 1, 1, tzinfo=UTC), source="eth_tvl"
        )

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["total_points"] == 3
        eth_tvl = next(e for e in body["connectors"] if e["source"] == "eth_tvl")
        assert eth_tvl["total_points"] == 1

    async def test_expected_interval_seconds_matches_the_connectors_own_metadata(
        self, client: httpx.AsyncClient
    ) -> None:
        """Fear & Greed publishes daily — 86,400 seconds."""
        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["expected_interval_seconds"] == 86_400

    async def test_no_recorded_attempt_reports_null_timing_fields(
        self, client: httpx.AsyncClient
    ) -> None:
        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["last_attempt_at"] is None
        assert entry["last_attempt_success"] is None
        assert entry["next_sync_at"] is None

    async def test_last_attempt_is_the_newest_recorded_run_regardless_of_outcome(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        """Newest first: a failed attempt more recent than an older success
        is still the one reported, exactly like the health-status streak
        check reads the same rows."""
        await seed_runs(session_factory, [False, True, True])

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["last_attempt_at"] is not None
        assert entry["last_attempt_success"] is False

    async def test_next_sync_at_projects_the_generic_schedulers_own_interval(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        """Fear & Greed is `auto_synced=True` — the generic
        `ExternalDataSyncScheduler`'s own interval applies, never Marketaux's
        dedicated `NewsSyncScheduler` interval."""
        from app.core.config import get_settings

        started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        async with session_factory() as session:
            session.add(
                ConnectorSyncRun(
                    source="fear_greed",
                    started_at=started,
                    completed_at=started,
                    success=True,
                    received=1,
                    inserted=1,
                )
            )
            await session.commit()

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        expected = started + timedelta(seconds=get_settings().external_data_sync_interval_seconds)
        assert entry["last_attempt_at"] == started.isoformat().replace("+00:00", "Z")
        assert entry["next_sync_at"] == expected.isoformat().replace("+00:00", "Z")

    async def test_next_sync_at_projects_the_dedicated_news_scheduler_interval_for_marketaux(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        """`news_sentiment` is `auto_synced=False` — its own `NewsSyncScheduler`
        interval must be used, not the generic scheduler's, or the projected
        next-sync time would be wrong for the one source that differs."""
        from app.core.config import get_settings

        started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        async with session_factory() as session:
            session.add(
                ConnectorSyncRun(
                    source="news_sentiment",
                    started_at=started,
                    completed_at=started,
                    success=True,
                    received=1,
                    inserted=1,
                )
            )
            await session.commit()

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "news_sentiment")
        expected = started + timedelta(seconds=get_settings().news_sync_interval_seconds)
        assert entry["next_sync_at"] == expected.isoformat().replace("+00:00", "Z")
        # Sanity: the two scheduler intervals actually differ in this
        # codebase's real config, or this test would pass by accident.
        assert (
            get_settings().news_sync_interval_seconds
            != get_settings().external_data_sync_interval_seconds
        )


class TestHealthReason:
    """`health_reason`/`last_attempt_error` — added after a real, live gap:
    a bare `stale` pill on the Data Sources page could not tell a scheduler
    that had stopped ticking (an operational problem) apart from a
    scheduler ticking normally against a source with genuinely nothing new
    to report (a real but non-actionable data condition). Both looked
    identical without this. See `app.connectors.health.describe_health`.
    """

    async def test_healthy_has_no_reason(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_point(
            session_factory, value=42.0, timestamp=datetime.now(UTC) - timedelta(hours=1)
        )

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["health_status"] == "healthy"
        assert entry["health_reason"] is None
        assert entry["last_attempt_error"] is None

    async def test_never_ingested_with_no_attempt_names_that(
        self, client: httpx.AsyncClient
    ) -> None:
        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["health_status"] == "never_ingested"
        assert entry["health_reason"] == "No sync has been attempted for this source yet."

    async def test_failing_surfaces_the_real_error_message(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_point(
            session_factory, value=42.0, timestamp=datetime.now(UTC) - timedelta(hours=1)
        )
        await seed_runs(session_factory, [False, False, False])

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["health_status"] == "failing"
        assert entry["last_attempt_error"] == "upstream 503"
        assert entry["health_reason"] == "The last 3 sync attempts all failed: upstream 503"

    async def test_stale_with_a_scheduler_still_ticking_on_schedule_names_the_quiet_source(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        """The real Marketaux case found live on 2026-09-27: every sync
        attempt succeeds, but the upstream source itself has published
        nothing new — `next_sync_at` still lands in the future."""
        await seed_point(
            session_factory, value=42.0, timestamp=datetime.now(UTC) - timedelta(days=30)
        )
        async with session_factory() as session:
            session.add(
                ConnectorSyncRun(
                    source="fear_greed",
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    success=True,
                    received=0,
                    inserted=0,
                )
            )
            await session.commit()

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["health_status"] == "stale"
        assert entry["health_reason"] == (
            "The sync is running on schedule, but no new value has been published "
            "upstream recently — this source may genuinely have nothing new to report "
            "right now."
        )

    async def test_stale_with_no_attempt_on_record_names_the_scheduler_as_the_suspect(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        """The real local-dev case found live on 2026-09-27: the standalone
        `scheduler_main` process was never started after the API/scheduler
        split, so every source it owns went stale with zero recorded sync
        attempts at all — a fully overdue, not-just-quiet, `next_sync_at`."""
        await seed_point(
            session_factory, value=42.0, timestamp=datetime.now(UTC) - timedelta(days=30)
        )

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["health_status"] == "stale"
        assert entry["next_sync_at"] is None
        assert entry["health_reason"] == (
            "No sync has been attempted since this value was stored — the scheduler "
            "process that owns this source may not be running."
        )

    async def test_stale_with_an_overdue_next_sync_names_the_scheduler_as_the_suspect(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_point(
            session_factory, value=42.0, timestamp=datetime.now(UTC) - timedelta(days=30)
        )
        long_overdue = datetime.now(UTC) - timedelta(days=10)
        async with session_factory() as session:
            session.add(
                ConnectorSyncRun(
                    source="fear_greed",
                    started_at=long_overdue,
                    completed_at=long_overdue,
                    success=True,
                    received=1,
                    inserted=1,
                )
            )
            await session.commit()

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["health_status"] == "stale"
        assert entry["health_reason"] == (
            "The next sync is overdue — the scheduler process that owns this source "
            "may not be running."
        )


class TestConnectorHistoryEndpoint:
    async def test_returns_points_in_the_requested_inclusive_range(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_point(session_factory, value=30.0, timestamp=datetime(2026, 1, 1, tzinfo=UTC))
        await seed_point(session_factory, value=50.0, timestamp=datetime(2026, 1, 2, tzinfo=UTC))
        await seed_point(session_factory, value=70.0, timestamp=datetime(2026, 1, 3, tzinfo=UTC))

        response = await client.get(
            "/api/v1/connectors/fear_greed/history",
            params={"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "fear_greed"
        assert [item["value"] for item in body["items"]] == [30.0, 50.0]
        assert [item["timestamp"] for item in body["items"]] == [
            "2026-01-01T00:00:00Z",
            "2026-01-02T00:00:00Z",
        ]
        assert body["pagination"] == {
            "total": 2,
            "returned": 2,
            "has_more": False,
            "limit": 100,
            "offset": 0,
        }

    async def test_omitting_start_and_end_queries_all_history(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_point(session_factory, value=42.0, timestamp=datetime(2018, 6, 1, tzinfo=UTC))
        await seed_point(session_factory, value=55.0, timestamp=datetime(2026, 1, 1, tzinfo=UTC))

        body = (await client.get("/api/v1/connectors/fear_greed/history")).json()
        assert body["pagination"]["total"] == 2
        assert [item["value"] for item in body["items"]] == [42.0, 55.0]

    async def test_paginates_with_limit_and_offset(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        for day, value in ((1, 10.0), (2, 20.0), (3, 30.0)):
            await seed_point(
                session_factory, value=value, timestamp=datetime(2026, 1, day, tzinfo=UTC)
            )

        first = await client.get(
            "/api/v1/connectors/fear_greed/history", params={"limit": 2, "offset": 0}
        )
        first_body = first.json()
        assert [item["value"] for item in first_body["items"]] == [10.0, 20.0]
        assert first_body["pagination"]["has_more"] is True

        second = await client.get(
            "/api/v1/connectors/fear_greed/history", params={"limit": 2, "offset": 2}
        )
        second_body = second.json()
        assert [item["value"] for item in second_body["items"]] == [30.0]
        assert second_body["pagination"]["has_more"] is False

    async def test_returns_404_for_an_unknown_source(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/connectors/nope/history")
        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "connector_not_found"
        assert "fear_greed" in body["detail"]

    async def test_is_mounted_unversioned_too(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        assert (await client.get("/connectors/fear_greed/history")).status_code == 200
