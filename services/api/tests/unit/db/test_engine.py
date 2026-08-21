"""Unit tests for the database engine lifecycle and connectivity probe."""

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

import app.db.engine as engine_module
from app.db.engine import (
    build_engine,
    dispose_engine,
    get_engine,
    probe_database,
)


@pytest.fixture(autouse=True)
def reset_engine():
    """Ensure the module-level engine cache is empty around each test."""
    engine_module._engine = None
    yield
    engine_module._engine = None


def _settings(**overrides: object) -> SimpleNamespace:
    values = {
        "database_url": "",
        "db_pool_size": 5,
        "db_max_overflow": 10,
        "db_echo": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_get_engine_returns_none_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a configured URL the engine stays disabled."""
    monkeypatch.setattr(engine_module, "get_settings", lambda: _settings())
    assert get_engine() is None


@pytest.mark.asyncio
async def test_get_engine_caches_the_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """The engine is created once and reused across calls."""
    monkeypatch.setattr(
        engine_module,
        "get_settings",
        lambda: _settings(
        database_url="postgresql+asyncpg://u:p@localhost:5432/db",
    ),
    )
    engine = get_engine()
    assert isinstance(engine, AsyncEngine)
    assert get_engine() is engine
    await dispose_engine()
    assert get_engine() is not engine  # cache was cleared


@pytest.mark.asyncio
async def test_build_engine_forwards_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pool sizing and echo settings reach the engine constructor."""
    monkeypatch.setattr(
        engine_module,
        "get_settings",
        lambda: _settings(
            database_url="postgresql+asyncpg://u:p@localhost:5432/db",
            db_pool_size=3,
            db_max_overflow=7,
            db_echo=True,
        ),
    )
    engine = build_engine()
    assert isinstance(engine, AsyncEngine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_dispose_engine_is_idempotent() -> None:
    """Disposing without an engine is a no-op."""
    await dispose_engine()
    await dispose_engine()


@pytest.mark.asyncio
async def test_probe_database_reports_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probing without a database returns a stable error message."""
    monkeypatch.setattr(engine_module, "get_settings", lambda: _settings())
    assert await probe_database() == "database is not configured"


@pytest.mark.asyncio
async def test_probe_database_succeeds_against_live_engine() -> None:
    """Probing a reachable engine returns ``None``."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    engine_module._engine = engine
    try:
        assert await probe_database() is None
    finally:
        await dispose_engine()


@pytest.mark.asyncio
async def test_probe_database_reports_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probing an unreachable engine returns the failure message."""
    engine = create_async_engine("sqlite+aiosqlite:////definitely/missing/dir/db.sqlite")
    engine_module._engine = engine
    try:
        error = await probe_database()
        assert error is not None
        assert "unable to open database file" in error
    finally:
        await dispose_engine()