"""A connector entering `failing` raises a real error-tracking event.

The health status is computed on read, so before this nothing watched the
*transition*: a connector could start failing at 3am and stay red until
someone opened the dashboard. These tests drive the real path (the shared
`record_sync_run`, and the real `ExternalDataSyncScheduler`) against a
real database engine and assert on the event the SDK would have sent.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.connectors.base import ConnectorMetadata
from app.connectors.health import FAILING_STREAK
from app.repositories.connector_sync_runs import ConnectorSyncRunRepository
from app.services import external_data_sync
from app.services.connector_sync_runs import record_sync_run
from app.services.external_data_ingest import ExternalDataIngestReport
from app.services.external_data_sync import ExternalDataSyncScheduler
from tests.monitoring.conftest import Tracker

BASE = datetime(2026, 9, 1, tzinfo=UTC)


async def _record(
    engine: AsyncEngine, source: str, minute: int, *, success: bool, error: str | None = None
) -> None:
    await record_sync_run(
        engine,
        source=source,
        started_at=BASE + timedelta(minutes=minute),
        success=success,
        received=1 if success else 0,
        error_message=None if success else (error or "upstream 503"),
    )


def _alerts(tracker: Tracker, source: str | None = None) -> list[dict]:
    events = [e for e in tracker.events if e.get("tags", {}).get("connector")]
    return [e for e in events if source is None or e["tags"]["connector"] == source]


class TestAlertOnTransition:
    async def test_no_alert_until_the_streak_completes(
        self, engine: AsyncEngine, tracker: Tracker
    ) -> None:
        for minute in range(FAILING_STREAK - 1):
            await _record(engine, "fear_greed", minute, success=False)
        assert tracker.events == []

    async def test_the_third_consecutive_failure_raises_one_real_alert(
        self, engine: AsyncEngine, tracker: Tracker
    ) -> None:
        errors = ["timeout 1", "timeout 2", "upstream 503"]
        for minute, error in enumerate(errors):
            await _record(engine, "fear_greed", minute, success=False, error=error)

        assert len(tracker.events) == 1
        alert = tracker.events[0]
        assert alert["level"] == "error"
        assert alert["message"] == (
            "Connector fear_greed is failing: its last 3 sync attempts all errored"
        )
        assert alert["tags"]["connector"] == "fear_greed"
        assert alert["fingerprint"] == ["connector-failing", "fear_greed"]
        health = alert["contexts"]["connector_health"]
        assert health["source"] == "fear_greed"
        assert health["consecutive_failures"] == FAILING_STREAK
        # Newest first: why it is failing, in the alert itself.
        assert health["recent_errors"] == ["upstream 503", "timeout 2", "timeout 1"]

    async def test_a_continuing_outage_alerts_once_not_every_tick(
        self, engine: AsyncEngine, tracker: Tracker
    ) -> None:
        """A connector failing hourly for a week must be one issue, not 168."""
        for minute in range(FAILING_STREAK + 10):
            await _record(engine, "fear_greed", minute, success=False)
        assert len(_alerts(tracker)) == 1

    async def test_a_recovery_then_a_second_outage_alerts_again(
        self, engine: AsyncEngine, tracker: Tracker
    ) -> None:
        minute = 0
        for _ in range(FAILING_STREAK):
            await _record(engine, "fear_greed", minute, success=False)
            minute += 1
        await _record(engine, "fear_greed", minute, success=True)
        minute += 1
        for _ in range(FAILING_STREAK):
            await _record(engine, "fear_greed", minute, success=False)
            minute += 1
        assert len(_alerts(tracker)) == 2

    async def test_a_success_in_the_streak_prevents_the_alert(
        self, engine: AsyncEngine, tracker: Tracker
    ) -> None:
        await _record(engine, "fear_greed", 0, success=False)
        await _record(engine, "fear_greed", 1, success=True)
        await _record(engine, "fear_greed", 2, success=False)
        await _record(engine, "fear_greed", 3, success=False)
        assert tracker.events == []

    async def test_one_connectors_failures_never_alert_for_another(
        self, engine: AsyncEngine, tracker: Tracker
    ) -> None:
        for minute in range(FAILING_STREAK):
            await _record(engine, "eth_tvl", minute, success=False)
        assert [e["tags"]["connector"] for e in _alerts(tracker)] == ["eth_tvl"]

    async def test_a_secret_in_a_recorded_error_message_is_redacted_in_the_alert(
        self, engine: AsyncEngine, tracker: Tracker
    ) -> None:
        secret = "ALERT" + "SECRET"
        for minute in range(FAILING_STREAK):
            await _record(
                engine,
                "eth_gas_price",
                minute,
                success=False,
                error=f"401 for https://api.example/v2/api?apikey={secret}&module=gastracker",
            )
        assert secret not in tracker.wire_text
        assert "apikey=[Filtered]" in tracker.wire_text

    async def test_a_successful_run_never_alerts(
        self, engine: AsyncEngine, tracker: Tracker
    ) -> None:
        for minute in range(FAILING_STREAK + 2):
            await _record(engine, "fear_greed", minute, success=True)
        assert tracker.events == []

    async def test_the_alert_does_not_change_what_is_recorded(
        self, engine: AsyncEngine, tracker: Tracker
    ) -> None:
        for minute in range(FAILING_STREAK):
            await _record(engine, "fear_greed", minute, success=False)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            runs = await ConnectorSyncRunRepository(session).list_recent("fear_greed", limit=10)
        assert len(runs) == FAILING_STREAK
        assert not any(run.success for run in runs)


class TestWithErrorTrackingDisabled:
    async def test_recording_failures_is_unaffected_when_no_dsn_is_configured(
        self, engine: AsyncEngine
    ) -> None:
        """No tracker fixture: the SDK is off, so alerting is a no-op and
        must not raise or change the recorded history."""
        for minute in range(FAILING_STREAK + 1):
            await _record(engine, "fear_greed", minute, success=False)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            runs = await ConnectorSyncRunRepository(session).list_recent("fear_greed", limit=10)
        assert len(runs) == FAILING_STREAK + 1


class TestThroughTheRealScheduler:
    async def test_three_real_failing_ticks_raise_one_alert(
        self, engine: AsyncEngine, tracker: Tracker, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole path an operator depends on: scheduler tick -> failed
        ingest -> recorded run -> failing transition -> alert."""

        async def failing_ingest(
            *, source: str, start: datetime, end: datetime
        ) -> ExternalDataIngestReport:
            raise RuntimeError(f"{source} is down")

        async def window(source: str, now: datetime) -> tuple[datetime, datetime]:
            return now - timedelta(days=1), now

        monkeypatch.setattr(external_data_sync, "get_engine", lambda: engine)
        monkeypatch.setattr(external_data_sync, "load_builtin_connectors", lambda: None)
        monkeypatch.setattr(
            external_data_sync.default_connector_registry, "has", lambda source: True
        )
        monkeypatch.setattr(
            external_data_sync.default_connector_registry,
            "describe",
            lambda source: ConnectorMetadata(source=source, label=source, description="x"),
        )
        monkeypatch.setattr(external_data_sync, "ingest_external_data", failing_ingest)
        scheduler = ExternalDataSyncScheduler(sources=["fear_greed"])
        monkeypatch.setattr(scheduler, "_catch_up_window", window)

        for tick in range(FAILING_STREAK + 2):
            summary = await scheduler.run_catch_up()
            assert summary.failed == 1
            expected_alerts = 0 if tick < FAILING_STREAK - 1 else 1
            assert len(_alerts(tracker)) == expected_alerts, f"after tick {tick + 1}"

        alert = _alerts(tracker)[0]
        assert alert["contexts"]["connector_health"]["recent_errors"][0] == "fear_greed is down"
