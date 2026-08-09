"""Async session management.

Provides the FastAPI dependency that yields an ``AsyncSession`` per request.
The session factory is bound to the lazily-created engine at call time, so
no global state is shared between the engine and session layers.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import get_engine


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield a database session for the duration of a request.

    The session is closed when the request completes; callers are expected
    to ``await session.commit()`` explicitly.
    """
    engine = get_engine()
    if engine is None:
        raise RuntimeError("Database is not configured")

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
