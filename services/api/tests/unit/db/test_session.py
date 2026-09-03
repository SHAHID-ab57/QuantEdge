"""Unit tests for the database session dependency."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.db.session as session_module
from app.db.session import get_db, get_db_or_none


async def _advance(agen) -> object:
    """Advance an async generator once, returning the first value."""
    return await anext(agen)


async def _finish(agen) -> None:
    """Exhaust the remainder of an async generator (teardown helper)."""
    try:
        async for _ in agen:
            pass
    except Exception:
        pass


async def test_get_db_raises_without_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a configured engine, the dependency fails loudly."""
    monkeypatch.setattr(session_module, "get_engine", lambda: None)
    with pytest.raises(RuntimeError, match="not configured"):
        await _advance(get_db())


async def test_get_db_yields_session_with_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With an engine, the dependency yields a usable session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(session_module, "get_engine", lambda: engine)
    gen = get_db()
    session = await _advance(gen)
    assert isinstance(session, AsyncSession)
    assert session.is_active
    await _finish(gen)


async def test_get_db_or_none_yields_none_without_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lenient dependency yields ``None`` when no engine exists."""
    monkeypatch.setattr(session_module, "get_engine", lambda: None)
    assert await _advance(get_db_or_none()) is None


async def test_get_db_or_none_yields_session_with_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lenient dependency yields a real session when configured."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(session_module, "get_engine", lambda: engine)
    gen = get_db_or_none()
    session = await _advance(gen)
    assert isinstance(session, AsyncSession)
    await _finish(gen)
