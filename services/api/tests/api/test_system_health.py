"""API tests for the platform system health/status/metrics endpoints.

Uses fakes for the runtime (no network, no database): the endpoints are
exercised through dependency overrides, and the unconfigured-database path
is covered by the repo-wide empty ``DATABASE_URL``.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.endpoints.system import _overall
from app.integrations.delta.websocket.client import (
    DeltaConnectionSnapshot,
    DeltaWebSocketClient,
)
from app.runtime import DeltaRestProbeResult, Runtime, get_runtime
from app.schemas.system import ComponentStatus, SystemHealthResponse


class FakeWs:
    """Minimal WebSocket client stub with a fixed connection snapshot."""

    def __init__(
        self,
        *,
        connected: bool = False,
        state: str = "disconnected",
        authenticated: bool = False,
        subscriptions: tuple[str, ...] = (),
        messages_received: int = 0,
        connection_attempts: int = 1,
        last_message_at: datetime | None = None,
    ) -> None:
        self._snapshot = DeltaConnectionSnapshot(
            state=state,  # type: ignore[arg-type]
            connected=connected,
            authenticated=authenticated,
            public=True,
            subscriptions=subscriptions,
            requested_subscriptions=subscriptions,
            last_message_at=last_message_at,
            last_heartbeat_at=None,
            connected_at=datetime.now(UTC) if connected else None,
            messages_received=messages_received,
            connection_attempts=connection_attempts,
            reconnects=max(connection_attempts - 1, 0),
            uptime_seconds=30.0 if connected else None,
        )

    def connection_snapshot(self) -> DeltaConnectionSnapshot:
        return self._snapshot


class FakeRuntime(Runtime):
    """Runtime with a fixed Delta REST probe and no live components."""

    def __init__(self, *, probe: DeltaRestProbeResult) -> None:
        super().__init__(
            market_data_live=False,
            symbols=(),
            started_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        self._probe = probe

    async def probe_delta_rest(self) -> DeltaRestProbeResult:
        return self._probe


@pytest.fixture(autouse=True)
def override_runtime(app: FastAPI) -> Iterator[None]:
    """Override the runtime dependency for every test in this module."""
    runtime = FakeRuntime(probe=DeltaRestProbeResult(ok=True, latency_ms=12.5, error=None))
    app.dependency_overrides[get_runtime] = lambda: runtime
    yield
    app.dependency_overrides.clear()


async def test_health_all_ok_shape(client: httpx.AsyncClient) -> None:
    """With a healthy fake runtime, every component reports its state."""
    response = await client.get("/api/v1/system/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"  # database is unavailable in tests
    assert body["api"]["name"] == "api"
    assert body["api"]["status"] == "ok"
    assert body["api"]["detail"] == "serving requests"
    assert body["database"]["status"] == "unavailable"
    assert body["database"]["detail"] == "database is not configured"
    assert body["delta_rest"]["status"] == "ok"
    assert body["delta_rest"]["latency_ms"] == 12.5
    assert "12ms" in body["delta_rest"]["detail"]
    assert body["delta_ws"]["status"] == "unavailable"
    assert body["delta_ws"]["state"] == "stopped"
    assert body["event_bus"]["status"] == "ok"
    assert body["state_manager"]["status"] == "ok"
    assert "subscribers" in body["event_bus"]["detail"]


async def test_health_delta_rest_failure(client: httpx.AsyncClient, app: FastAPI) -> None:
    """A failing Delta probe marks the component and overall status."""
    runtime = FakeRuntime(
        probe=DeltaRestProbeResult(ok=False, latency_ms=250.0, error="Connection refused")
    )
    app.dependency_overrides[get_runtime] = lambda: runtime
    body = (await client.get("/api/v1/system/health")).json()
    assert body["status"] == "unavailable"
    assert body["delta_rest"]["status"] == "unavailable"
    assert body["delta_rest"]["detail"] == "Connection refused"


async def test_health_ws_connected(client: httpx.AsyncClient, app: FastAPI) -> None:
    """A running, connected WebSocket client reports ok with live state."""
    runtime = FakeRuntime(probe=DeltaRestProbeResult(ok=True, latency_ms=10.0, error=None))
    runtime.delta_ws = cast(
        DeltaWebSocketClient,
        FakeWs(
            connected=True,
            state="connected",
            subscriptions=("trades", "ticker"),
            messages_received=120,
        ),
    )
    app.dependency_overrides[get_runtime] = lambda: runtime
    body = (await client.get("/api/v1/system/health")).json()
    assert body["status"] == "unavailable"  # database still unavailable
    assert body["delta_ws"]["status"] == "ok"
    assert body["delta_ws"]["state"] == "connected"
    assert body["delta_ws"]["uptime_seconds"] == 30.0
    assert body["delta_ws"]["latency_ms"] is None
    assert "2 subscription(s)" in body["delta_ws"]["detail"]


async def test_health_ws_connected_staleness(client: httpx.AsyncClient, app: FastAPI) -> None:
    """A connected socket with a recent message reports message staleness."""
    runtime = FakeRuntime(probe=DeltaRestProbeResult(ok=True, latency_ms=10.0, error=None))
    runtime.delta_ws = cast(
        DeltaWebSocketClient,
        FakeWs(
            connected=True,
            state="connected",
            subscriptions=("ticker",),
            messages_received=10,
            last_message_at=datetime.now(UTC) - timedelta(seconds=3),
        ),
    )
    app.dependency_overrides[get_runtime] = lambda: runtime
    body = (await client.get("/api/v1/system/health")).json()
    assert body["delta_ws"]["status"] == "ok"
    assert body["delta_ws"]["latency_ms"] >= 2000
    assert "last message" in body["delta_ws"]["detail"]


async def test_health_ws_disconnected_degrades(client: httpx.AsyncClient, app: FastAPI) -> None:
    """A running but disconnected WebSocket reports degraded."""
    runtime = FakeRuntime(probe=DeltaRestProbeResult(ok=True, latency_ms=10.0, error=None))
    runtime.delta_ws = cast(DeltaWebSocketClient, FakeWs(connected=False))
    app.dependency_overrides[get_runtime] = lambda: runtime
    body = (await client.get("/api/v1/system/health")).json()
    assert body["delta_ws"]["status"] == "degraded"
    assert body["delta_ws"]["state"] == "disconnected"


async def test_overall_aggregation() -> None:
    """The overall status follows the worst component state."""
    ok = ComponentStatus(name="a", status="ok")
    degraded = ComponentStatus(name="b", status="degraded")
    unavailable = ComponentStatus(name="c", status="unavailable")
    assert _overall(ok, ok) == "ok"
    assert _overall(ok, degraded) == "degraded"
    assert _overall(ok, degraded, unavailable) == "unavailable"


async def test_status_reports_uptime_and_freshness(
    client: httpx.AsyncClient,
) -> None:
    """Status carries uptime, metadata, timeline, and null DB-derived fields."""
    response = await client.get("/api/v1/system/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"  # no database in tests
    assert body["uptime_seconds"] >= 0
    assert body["version"] == "0.1.0"
    assert body["market_data_live"] is False
    assert body["delta_ws_connected"] is False
    assert body["delta_ws"] is None
    assert body["last_ws_message_at"] is None
    assert body["last_heartbeat_at"] is None
    assert body["last_ws_reconnect_at"] is None
    assert body["last_rest_request_at"] is None
    assert body["last_ingestion_at"] is None  # no database in tests
    assert body["symbols_tracked"] == 0


async def test_status_reports_delta_connection_state(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """Status embeds the live WebSocket connection snapshot when running."""
    runtime = FakeRuntime(probe=DeltaRestProbeResult(ok=True, latency_ms=10.0, error=None))
    runtime.delta_ws = cast(
        DeltaWebSocketClient,
        FakeWs(
            connected=True,
            state="connected",
            subscriptions=("trades", "ticker"),
            messages_received=120,
            connection_attempts=2,
        ),
    )
    app.dependency_overrides[get_runtime] = lambda: runtime
    body = (await client.get("/api/v1/system/status")).json()
    assert body["delta_ws_connected"] is True
    ws = body["delta_ws"]
    assert ws["state"] == "connected"
    assert ws["connected"] is True
    assert ws["subscriptions"] == ["trades", "ticker"]
    assert ws["messages_received"] == 120
    assert ws["connection_attempts"] == 2
    assert ws["reconnects"] == 1
    assert ws["uptime_seconds"] == 30.0
    assert ws["connected_at"] is not None
    assert body["last_ws_reconnect_at"] == ws["connected_at"]


async def test_status_degraded_without_database(
    client: httpx.AsyncClient,
) -> None:
    """Without a database the overall status is degraded."""
    body = (await client.get("/api/v1/system/status")).json()
    assert body["status"] == "degraded"


async def test_metrics_offline_zeroes(client: httpx.AsyncClient) -> None:
    """Without live mode or a database, metrics are zeros and nulls."""
    response = await client.get("/api/v1/system/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["synchronized_markets"] is None
    assert body["stored_candles"] is None
    assert body["messages_received"] == 0
    assert body["messages_normalized"] == 0
    assert body["validation_failures"] == 0
    assert body["events_published"] == 0
    assert body["average_pipeline_latency_ms"] is None
    assert body["state_updates"] == 0
    assert body["state_symbols_tracked"] == 0
    assert body["state_latest_update_at"] is None
    assert body["state_latest_prices"] == {}
    assert body["event_bus_subscribers"] >= 4  # state manager attaches 4 handlers
    assert body["event_bus_pending"] == 0
    assert body["event_bus_published"] == 0
    assert body["event_bus_failed_handlers"] == 0
    assert body["event_bus_average_handler_latency_ms"] is None
    assert "collected_at" in body


async def test_metrics_reports_bus_and_state_activity(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """Published events and state snapshots flow into the metrics response."""
    runtime = FakeRuntime(probe=DeltaRestProbeResult(ok=True, latency_ms=10.0, error=None))
    app.dependency_overrides[get_runtime] = lambda: runtime

    from app.marketdata.bus_events import TickerUpdated
    from app.marketdata.models import TickerEvent

    event = TickerUpdated(
        source="test",
        ticker=TickerEvent(
            exchange="delta",
            symbol="BTCUSD",
            event_time=datetime.now(UTC),
            last_price=Decimal("65000.5"),
        ),
    )
    await runtime.bus.publish(event)

    body = (await client.get("/api/v1/system/metrics")).json()
    assert body["event_bus_published"] == 1
    assert body["state_symbols_tracked"] == 1  # handler completed synchronously
    assert "BTCUSD" in body["state_latest_prices"]
    assert body["state_latest_prices"]["BTCUSD"] == "65000.5"
    assert body["event_bus_average_handler_latency_ms"] is not None


async def test_system_endpoints_mounted_unversioned_too(
    client: httpx.AsyncClient,
) -> None:
    """The system router mirrors the legacy /health dual-mount pattern."""
    for path in ("/system/health", "/system/status", "/system/metrics"):
        response = await client.get(path)
        assert response.status_code == 200, path


async def test_system_schemas_validate(client: httpx.AsyncClient) -> None:
    """Response models round-trip through pydantic."""
    body = (await client.get("/api/v1/system/health")).json()
    parsed = SystemHealthResponse.model_validate(body)
    assert parsed.status == body["status"]
