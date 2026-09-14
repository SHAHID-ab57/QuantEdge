"""Async Redis client management (M5-E3-T1) — lazily created, exactly
mirroring `app.db.engine`'s own `get_engine`/`dispose_engine` pattern.

Redis backs three optional, defense-in-depth features — general rate
limiting, login lockout, and token revocation (`app.middleware
.rate_limit`, `app.auth.login_lockout`, `app.auth.token_revocation`) —
never anything load-bearing for core request handling. See
`ARCHITECTURE.md` § "Redis" for the full reasoning behind treating it as
a soft dependency: unconfigured degrades gracefully (in-process
fallback, exactly like an unset `DATABASE_URL`), configured-but-
unreachable at startup fails loudly (exactly like a configured-but-
unreachable database), and a connection that drops mid-runtime after a
successful startup fails open on a per-call basis with a logged warning
(never blocks otherwise-unrelated request handling).
"""

import logging

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis | None:
    """Return the cached Redis client, creating it on first use.

    Returns ``None`` when no `REDIS_URL` is configured, so Redis-backed
    features can fall back to their in-process equivalents.
    """
    global _client

    if _client is None:
        settings = get_settings()
        if not settings.redis_url:
            return None
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def dispose_redis_client() -> None:
    """Close and release the cached client, if one was ever created."""
    global _client

    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("Redis client disposed")


async def probe_redis() -> str | None:
    """Verify Redis connectivity.

    Returns ``None`` on success or an error message on failure — the
    same contract `app.db.engine.probe_database` already follows.
    """
    client = get_redis_client()
    if client is None:
        return "Redis is not configured"

    try:
        await client.ping()
    except Exception as exc:  # noqa: BLE001 - surfaced as a plain string, not re-raised
        return str(exc)
    return None
