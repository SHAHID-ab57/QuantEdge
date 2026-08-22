"""API tests for the live market-stream WebSocket gateway (``/ws/market``).

Uses Starlette's synchronous ``TestClient`` for the WebSocket wire
protocol. Bus-driven fan-out itself (the concurrency-sensitive part) is
covered at the unit level in ``tests/unit/marketdata/test_gateway.py``;
these tests only verify the route's protocol handling and its wiring to
a fresh, per-test ``Runtime`` (never the process-wide singleton).
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.marketdata.bus_events import TradeEventReceived
from app.marketdata.models import TradeEvent
from app.runtime import Runtime, get_runtime


@pytest.fixture
def runtime() -> Runtime:
    """A fresh runtime — never the process-wide singleton — per test."""
    return Runtime(market_data_live=False, symbols=(), started_at=datetime.now(UTC))


@pytest.fixture(autouse=True)
def override_runtime(app: FastAPI, runtime: Runtime) -> None:
    app.dependency_overrides[get_runtime] = lambda: runtime
    yield
    app.dependency_overrides.clear()


def test_ping_receives_a_pong(app: FastAPI) -> None:
    with TestClient(app).websocket_connect("/api/v1/ws/market") as ws:
        ws.send_json({"action": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_subscribe_with_no_prior_state_returns_an_empty_snapshot(app: FastAPI) -> None:
    with TestClient(app).websocket_connect("/api/v1/ws/market") as ws:
        ws.send_json({"action": "subscribe", "symbols": ["ETHUSD"]})
        assert ws.receive_json() == {
            "type": "snapshot",
            "symbol": "ETHUSD",
            "trade": None,
            "ticker": None,
        }


async def test_subscribe_with_existing_state_returns_a_populated_snapshot(
    app: FastAPI, runtime: Runtime
) -> None:
    trade = TradeEvent(
        exchange="delta",
        symbol="ETHUSD",
        event_time=datetime.now(UTC),
        side="unknown",
        price=Decimal("1950.25"),
        size=Decimal("3"),
    )
    # Populate state directly (bypassing the bus) so this test has no
    # cross-thread dependency on the WebSocket connection's own event loop.
    await runtime.state_manager._on_trade_received(TradeEventReceived(source="test", trade=trade))

    with TestClient(app).websocket_connect("/api/v1/ws/market") as ws:
        ws.send_json({"action": "subscribe", "symbols": ["ethusd"]})
        message = ws.receive_json()
        assert message["symbol"] == "ETHUSD"
        assert message["trade"]["price"] == "1950.25"
        assert message["trade"]["size"] == "3"


def test_unknown_action_returns_an_error_and_keeps_the_connection_open(
    app: FastAPI,
) -> None:
    with TestClient(app).websocket_connect("/api/v1/ws/market") as ws:
        ws.send_json({"action": "levitate"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "levitate" in error["detail"]

        ws.send_json({"action": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_invalid_json_returns_an_error_and_keeps_the_connection_open(
    app: FastAPI,
) -> None:
    with TestClient(app).websocket_connect("/api/v1/ws/market") as ws:
        ws.send_text("not json")
        error = ws.receive_json()
        assert error == {"type": "error", "detail": "invalid JSON"}

        ws.send_json({"action": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_malformed_subscribe_message_returns_a_validation_error(app: FastAPI) -> None:
    with TestClient(app).websocket_connect("/api/v1/ws/market") as ws:
        ws.send_json({"action": "subscribe", "symbols": "ETHUSD"})  # must be a list
        error = ws.receive_json()
        assert error["type"] == "error"


def test_disconnecting_unregisters_the_connection(app: FastAPI, runtime: Runtime) -> None:
    with TestClient(app).websocket_connect("/api/v1/ws/market") as ws:
        ws.send_json({"action": "subscribe", "symbols": ["ETHUSD"]})
        ws.receive_json()
        assert runtime.gateway.connection_count() == 1

    assert runtime.gateway.connection_count() == 0
    assert runtime.gateway.subscriber_count("ETHUSD") == 0
