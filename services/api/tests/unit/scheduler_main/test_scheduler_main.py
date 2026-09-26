"""Unit tests for the standalone scheduler process (`app.scheduler_main`).

Mirrors `tests/unit/runtime/test_runtime.py`'s own coverage for the five
schedulers this module took over from `Runtime` — see
`docs/infrastructure/EVENT_LOOP_SEPARATION_DESIGN.md`.
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import app.scheduler_main as scheduler_main_module
from app.core.config import Settings
from app.scheduler_main import (
    HEARTBEAT_INTERVAL_SECONDS,
    Schedulers,
    _heartbeat_loop,
    _start_schedulers,
    _stop_schedulers,
    run,
)


def _settings(**overrides: object) -> Settings:
    values = {
        "candle_sync_enabled": False,
        "candle_sync_interval_seconds": 300,
        "candle_sync_backfill_days": 3,
        "prediction_grading_enabled": False,
        "prediction_grading_interval_seconds": 300,
        "external_data_sync_enabled": False,
        "external_data_sync_interval_seconds": 3600,
        "external_data_sync_sources": "",
        "external_data_sync_backfill_days": 3650,
        "news_sync_enabled": False,
        "news_sync_interval_seconds": 21600,
        "news_sync_backfill_days": 3650,
        "retraining_scheduler_enabled": False,
        "retraining_experiment_ids": "",
        "retraining_tick_interval_seconds": 3600,
        "retraining_min_interval_seconds": 168 * 3600,
        "retraining_window_hours": 8760,
    }
    values.update(overrides)
    # A duck-typed stand-in, not a real `Settings` -- matches
    # `tests/unit/runtime/test_runtime.py`'s own `_settings()` helper
    # exactly, `cast` here only to satisfy `_start_schedulers`' stricter
    # `Settings`-typed parameter (unlike `Runtime.start`, which always
    # reads settings via `get_settings()` rather than taking them directly).
    return cast(Settings, SimpleNamespace(**values))


class _FakeScheduler:
    """Scripted stand-in for any of the five scheduler classes."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


@pytest.fixture(autouse=True)
def _no_real_env_file_duplicates(monkeypatch: pytest.MonkeyPatch):
    """Isolate these tests from whatever the real local `.env` contains —
    mirrors `tests/unit/core/test_application.py`'s own fixture of the
    same name and purpose."""
    monkeypatch.setattr(scheduler_main_module, "find_duplicate_env_keys", lambda path: [])


async def test_start_schedulers_all_disabled_returns_all_none() -> None:
    """No scheduler starts when every gate is off."""
    schedulers = await _start_schedulers(_settings())
    assert schedulers == Schedulers()


async def test_start_schedulers_starts_candle_sync_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scheduler_main_module, "CandleSyncScheduler", _FakeScheduler)
    schedulers = await _start_schedulers(_settings(candle_sync_enabled=True))
    assert schedulers.candle_sync is not None
    assert schedulers.candle_sync.started is True  # type: ignore[attr-defined]


async def test_start_schedulers_starts_prediction_grading_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scheduler_main_module, "PredictionGradingScheduler", _FakeScheduler)
    schedulers = await _start_schedulers(_settings(prediction_grading_enabled=True))
    assert schedulers.prediction_grading is not None
    assert schedulers.prediction_grading.started is True  # type: ignore[attr-defined]


async def test_start_schedulers_starts_external_data_sync_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scheduler_main_module, "ExternalDataSyncScheduler", _FakeScheduler)
    schedulers = await _start_schedulers(_settings(external_data_sync_enabled=True))
    assert schedulers.external_data_sync is not None
    assert schedulers.external_data_sync.started is True  # type: ignore[attr-defined]


async def test_start_schedulers_starts_news_sync_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scheduler_main_module, "NewsSyncScheduler", _FakeScheduler)
    schedulers = await _start_schedulers(_settings(news_sync_enabled=True))
    assert schedulers.news_sync is not None
    assert schedulers.news_sync.started is True  # type: ignore[attr-defined]


async def test_start_schedulers_starts_retraining_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scheduler_main_module, "RetrainingScheduler", _FakeScheduler)
    schedulers = await _start_schedulers(
        _settings(
            retraining_scheduler_enabled=True,
            retraining_experiment_ids="6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
        )
    )
    assert schedulers.retraining is not None
    assert schedulers.retraining.started is True  # type: ignore[attr-defined]


async def test_stop_schedulers_stops_only_the_ones_that_started() -> None:
    started = _FakeScheduler()
    schedulers = Schedulers(candle_sync=started)  # type: ignore[arg-type]
    await _stop_schedulers(schedulers)
    assert started.stopped is True


async def test_stop_schedulers_is_a_noop_when_none_started() -> None:
    await _stop_schedulers(Schedulers())


async def test_heartbeat_loop_touches_the_file_before_stopping(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "heartbeat"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(scheduler_main_module, "HEARTBEAT_PATH", heartbeat_path)
        stop = asyncio.Event()
        task = asyncio.create_task(_heartbeat_loop(stop))
        # Yield to the loop enough times for the first write to happen
        # before signaling the loop to stop -- `_heartbeat_loop` checks
        # `stop.is_set()` *before* writing, so setting it immediately
        # (with no yield at all) would skip the write entirely.
        for _ in range(5):
            await asyncio.sleep(0)
        stop.set()
        await task
    assert heartbeat_path.exists()


async def test_run_raises_on_conflicting_env_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.env_validation import DuplicateEnvKey

    monkeypatch.setattr(
        scheduler_main_module,
        "find_duplicate_env_keys",
        lambda path: [DuplicateEnvKey(key="FOO", occurrences=((1, "a"), (2, "b")))],
    )
    with pytest.raises(RuntimeError, match="Conflicting duplicate"):
        await run()


async def test_run_raises_when_database_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler_main_module, "get_settings", lambda: _settings())
    monkeypatch.setattr(scheduler_main_module, "get_engine", lambda: None)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not configured"):
        await run()


async def test_run_raises_when_database_probe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler_main_module, "get_settings", lambda: _settings())
    monkeypatch.setattr(scheduler_main_module, "get_engine", lambda: object())
    monkeypatch.setattr(
        scheduler_main_module, "probe_database", _async_return("connection refused")
    )
    with pytest.raises(RuntimeError, match="connection refused"):
        await run()


async def test_run_full_cycle_starts_and_stops_schedulers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A full run: startup checks pass, the enabled scheduler starts, and
    (since `stop` is pre-set) shutdown runs immediately afterward — no real
    signal needed, per `run`'s own `stop` parameter docstring."""
    monkeypatch.setattr(
        scheduler_main_module, "get_settings", lambda: _settings(candle_sync_enabled=True)
    )
    monkeypatch.setattr(scheduler_main_module, "get_engine", lambda: object())
    monkeypatch.setattr(scheduler_main_module, "probe_database", _async_return(None))
    monkeypatch.setattr(scheduler_main_module, "CandleSyncScheduler", _FakeScheduler)
    disposed = []
    monkeypatch.setattr(scheduler_main_module, "dispose_engine", _async_append(disposed))
    monkeypatch.setattr(scheduler_main_module, "HEARTBEAT_PATH", tmp_path / "heartbeat")

    stop = asyncio.Event()
    stop.set()
    result = await run(stop)

    assert result == 0
    assert disposed == [True]


def _async_return(value: object):
    async def _inner(*_args: object, **_kwargs: object) -> object:
        return value

    return _inner


def _async_append(sink: list[object]):
    async def _inner(*_args: object, **_kwargs: object) -> None:
        sink.append(True)

    return _inner


def test_heartbeat_interval_is_short_relative_to_retraining_ticks() -> None:
    """The whole point of a dedicated heartbeat is that it can't be
    confused with `RetrainingScheduler`'s legitimately-hour-plus-long
    quiet periods."""
    assert HEARTBEAT_INTERVAL_SECONDS < 60
