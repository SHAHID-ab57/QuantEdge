"""Unit tests for the runtime composition root (start/stop/probe)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import app.runtime as runtime_module
from app.runtime import (
    DeltaRestProbeResult,
    Runtime,
    build_runtime,
    get_runtime,
    shutdown_runtime,
    start_runtime,
)


def _settings(**overrides: object) -> SimpleNamespace:
    values = {
        "market_data_live": False,
        "delta_market_symbols": "ETHUSD, BTCUSD",
        "candle_sync_enabled": False,
        "candle_sync_interval_seconds": 300,
        "candle_sync_backfill_days": 3,
        "delta_base_url": "https://api.test.invalid",
        "delta_api_key": "",
        "delta_api_secret": "",
        "delta_request_timeout": 10.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeDeltaWS:
    """Scripted stand-in for the Delta WebSocket client."""

    def __init__(self) -> None:
        self.listeners: list[tuple[str, object]] = []
        self.subscriptions: list[tuple[str, object]] = []
        self.started = False
        self.closed = False

    def add_listener(self, channel: str, handler: object) -> None:
        self.listeners.append((channel, handler))

    async def subscribe(self, channel: str, symbols: object) -> None:
        self.subscriptions.append((channel, symbols))

    def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    def connection_snapshot(self) -> object:
        return "snapshot"


class FakeDeltaClient:
    """Stand-in for DeltaClient with a scripted ``get`` outcome."""

    def __init__(self, response: object | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.closed = False
        self.requested: list[tuple[str, dict]] = []

    async def get(self, path: str, params: dict | None = None) -> object:
        self.requested.append((path, params or {}))
        if self.error is not None:
            raise self.error
        return self.response

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def reset_runtime():
    """Keep the process-wide runtime clean between tests."""
    runtime_module._runtime = None
    yield
    runtime_module._runtime = None


def _runtime(market_data_live: bool = False) -> Runtime:
    return Runtime(
        market_data_live=market_data_live,
        symbols=("ETHUSD",),
        started_at=datetime.now(UTC),
    )


async def test_shutdown_runtime_without_runtime_is_noop() -> None:
    """Shutting down an unstarted process-wide runtime does nothing."""
    await shutdown_runtime()


async def test_build_runtime_reads_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The runtime is built from settings, with symbols split on commas."""
    monkeypatch.setattr(runtime_module, "get_settings", lambda: _settings())
    runtime = build_runtime()
    assert runtime.market_data_live is False
    assert runtime._symbols == ("ETHUSD", "BTCUSD")  # noqa: SLF001
    assert runtime.bus is not None
    assert runtime.state_manager is not None
    assert get_runtime() is runtime  # cached


async def test_start_and_shutdown_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline start keeps the pipeline and WebSocket client absent."""
    monkeypatch.setattr(runtime_module, "get_settings", lambda: _settings())
    await start_runtime()
    runtime = get_runtime()
    assert runtime.pipeline is None
    assert runtime.delta_ws is None
    assert runtime.candle_sync is None

    await shutdown_runtime()
    assert runtime_module._runtime is None


async def test_start_live_wires_pipeline_and_ws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live mode subscribes to every channel and starts the client."""
    settings = _settings(market_data_live=True)
    monkeypatch.setattr(runtime_module, "get_settings", lambda: settings)
    fake_ws = FakeDeltaWS()
    monkeypatch.setattr(runtime_module, "get_delta_ws_client", lambda: fake_ws)

    await start_runtime()
    runtime = get_runtime()
    assert runtime.pipeline is not None
    assert runtime.delta_ws is fake_ws
    assert fake_ws.started is True
    channels = [channel for channel, _ in fake_ws.subscriptions]
    assert channels == ["trades", "ticker", "ob_l1", "ob_updates"]

    await shutdown_runtime()
    assert fake_ws.closed is True
    assert runtime_module._runtime is None


async def test_runtime_shutdown_stops_candle_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The candle sync scheduler is stopped when configured."""
    stopped = []

    class FakeSync:
        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            stopped.append(True)

    monkeypatch.setattr(
        runtime_module,
        "get_settings",
        lambda: _settings(candle_sync_enabled=True),
    )
    monkeypatch.setattr(runtime_module, "CandleSyncScheduler", lambda **_: FakeSync())

    runtime = _runtime()
    await runtime.start()
    assert runtime.candle_sync is not None
    await runtime.shutdown()
    assert stopped == [True]
    assert runtime.candle_sync is None


async def test_delta_connection_none_when_not_running() -> None:
    """Without a WebSocket client the snapshot is ``None``."""
    runtime = _runtime()
    assert runtime.delta_connection() is None


async def test_delta_connection_snapshot_when_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """A connected client exposes its connection snapshot."""
    monkeypatch.setattr(runtime_module, "get_delta_ws_client", lambda: FakeDeltaWS())
    runtime = _runtime(market_data_live=True)
    runtime.delta_ws = FakeDeltaWS()  # type: ignore[assignment]
    assert runtime.delta_connection() == "snapshot"


async def test_probe_delta_rest_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful probe reports ok with a latency."""
    fake = FakeDeltaClient(response={"results": []})
    monkeypatch.setattr(runtime_module, "DeltaClient", lambda *a, **k: fake)
    monkeypatch.setattr(runtime_module, "get_settings", lambda: _settings())

    runtime = _runtime()
    result = await runtime.probe_delta_rest()
    assert isinstance(result, DeltaRestProbeResult)
    assert result.ok is True
    assert result.error is None
    assert result.latency_ms is not None
    assert result.latency_ms >= 0
    assert fake.closed is True
    assert runtime.last_rest_request_at is not None
    assert fake.requested[0][0] == "/v2/products"


async def test_probe_delta_rest_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing probe reports unavailable without raising."""
    fake = FakeDeltaClient(error=ConnectionError("boom"))
    monkeypatch.setattr(runtime_module, "DeltaClient", lambda *a, **k: fake)
    monkeypatch.setattr(runtime_module, "get_settings", lambda: _settings())

    runtime = _runtime()
    result = await runtime.probe_delta_rest()
    assert result.ok is False
    assert result.error == "boom"
    assert result.latency_ms is not None
    assert fake.closed is True


async def test_ws_event_listener_stamps_message_time() -> None:
    """Dispatched WebSocket events stamp the runtime message timestamp."""
    runtime = _runtime(market_data_live=True)
    assert runtime.last_ws_message_at is None
    await runtime._on_ws_event(object())  # type: ignore[arg-type]
    assert runtime.last_ws_message_at is not None