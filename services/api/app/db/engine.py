"""Async SQLAlchemy engine management.

Provides a lazily-created, connection-pooled async engine plus a
connectivity probe used by the lifespan and health endpoint.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None


def build_engine() -> AsyncEngine:
    """Create the async engine from application settings."""
    settings = get_settings()
    logger.info(
        "Creating database engine (pool_size=%s, max_overflow=%s, pre_ping=true)",
        settings.db_pool_size,
        settings.db_max_overflow,
    )
    return create_async_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        echo=settings.db_echo,
        connect_args={"timeout": 5},
    )


def get_engine() -> AsyncEngine | None:
    """Return the cached engine, creating it on first use.

    Returns ``None`` when no database URL is configured, so services and
    tests can run without a database.
    """
    global _engine

    if _engine is None:
        settings = get_settings()
        if not settings.database_url:
            logger.warning("Database URL not configured; database engine disabled")
            return None
        _engine = build_engine()
    return _engine


async def dispose_engine() -> None:
    """Dispose the engine and release all pooled connections."""
    global _engine

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("Database engine disposed")


async def probe_database() -> str | None:
    """Verify database connectivity.

    Returns ``None`` on success or an error message on failure.
    """
    engine = get_engine()
    if engine is None:
        return "database is not configured"

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        return str(exc)
    return None
