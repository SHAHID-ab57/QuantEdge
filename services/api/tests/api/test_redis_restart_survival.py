"""Proves rate limiting and login lockout state survives an app restart
when Redis is configured (M5-E3-T1) — the exact opposite of what
M5-E2-T1 found and disclosed for the in-process fallback ("a process
restart silently clears both the rate limiter and the lockout tracker").

"Restart" is simulated the only way that's actually meaningful here: two
*separate* `create_app()` calls (so two entirely separate Python
`TokenBucketRateLimiter`/`LoginLockoutTracker`-or-Redis-equivalent
objects, exactly as a real process restart would produce), both pointed
at the *same* Redis instance/logical DB. State observed through the
second app that could only have come from the first proves it lived in
Redis, not in either app's own now-discarded in-memory objects.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
import redis.asyncio as redis
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

import app.application as application_module
import app.core.redis as redis_module
from app.core.config import Settings
from app.db.session import get_db
from tests.conftest import SessionFactory

pytestmark = pytest.mark.redis

_TEST_REDIS_URL = "redis://localhost:6379/15"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "jwt_secret_key": "redis-restart-test-only-secret",
        "database_url": "",
        "redis_url": _TEST_REDIS_URL,
        "rate_limit_requests": 2,
        "rate_limit_window_seconds": 60,
        "login_lockout_max_attempts": 2,
        "login_lockout_window_seconds": 60,
        "login_lockout_cooldown_seconds": 300,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


async def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: SessionFactory,
    **settings_overrides: object,
) -> tuple[FastAPI, httpx.AsyncClient, LifespanManager]:
    settings_factory_fn = lambda: _settings(**settings_overrides)  # noqa: E731
    monkeypatch.setattr(application_module, "get_settings", settings_factory_fn)
    # `app.core.redis.get_redis_client` calls its own `get_settings`
    # reference and caches the client it builds as a module-level
    # global — patch that reference too, and reset the cache, so each
    # simulated "instance" in this file builds its own fresh client
    # against the (correctly monkeypatched) settings, exactly as a real
    # process restart would, rather than reusing a stale cached client
    # from an earlier test or an earlier "instance" in this same test.
    monkeypatch.setattr(redis_module, "get_settings", settings_factory_fn)
    monkeypatch.setattr(redis_module, "_client", None)
    fastapi_app = application_module.create_app()

    # `POST /auth/login` needs a real database session (to look up the
    # — here, always-nonexistent — email), exactly like the root `app`
    # fixture's own override; `database_url=""` above keeps
    # `app.application.startup`'s own DB check skipped.
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    manager = LifespanManager(fastapi_app)
    await manager.__aenter__()
    transport = httpx.ASGITransport(app=fastapi_app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return fastapi_app, client, manager


class TestRateLimitSurvivesRestart:
    async def test_an_exhausted_bucket_is_still_exhausted_after_a_simulated_restart(
        self,
        monkeypatch: pytest.MonkeyPatch,
        redis_client: redis.Redis,
        session_factory: SessionFactory,
    ) -> None:
        # A high lockout threshold so only the rate limiter (capacity=2)
        # can possibly be what produces a 429 here — otherwise the two
        # mechanisms, both IP-keyed, could each independently trip on the
        # same requests and make it ambiguous which one actually fired.
        overrides: dict[str, object] = {"login_lockout_max_attempts": 100}

        # "Instance 1" — exhaust the tiny 2-request bucket for this IP.
        app1, client1, manager1 = await _build_client(monkeypatch, session_factory, **overrides)
        for _ in range(2):
            response = await client1.post(
                "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
            )
            assert response.status_code == 401
        exhausted = await client1.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
        )
        assert exhausted.status_code == 429
        assert exhausted.json()["code"] == "rate_limited"
        await client1.aclose()
        await manager1.__aexit__(None, None, None)

        # "Restart" — a brand new app, brand new in-memory objects, same Redis.
        app2, client2, manager2 = await _build_client(monkeypatch, session_factory, **overrides)
        assert app2.state.rate_limiter is not app1.state.rate_limiter  # genuinely a new object

        # The *first* request against the new "instance" is already
        # rejected — this could only be true if the bucket's state came
        # from Redis, since this object has never seen this key before.
        still_exhausted = await client2.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
        )
        assert still_exhausted.status_code == 429
        assert still_exhausted.json()["code"] == "rate_limited"
        await client2.aclose()
        await manager2.__aexit__(None, None, None)


class TestLoginLockoutSurvivesRestart:
    async def test_a_lockout_is_still_active_after_a_simulated_restart(
        self,
        monkeypatch: pytest.MonkeyPatch,
        redis_client: redis.Redis,
        session_factory: SessionFactory,
    ) -> None:
        # A high rate-limit capacity so only the lockout (max_attempts=2)
        # can possibly be what produces a 429 here — see the identical
        # reasoning in `TestRateLimitSurvivesRestart`, mirrored.
        overrides: dict[str, object] = {"rate_limit_requests": 100}

        # "Instance 1" — trip the 2-attempt lockout for this email.
        app1, client1, manager1 = await _build_client(monkeypatch, session_factory, **overrides)
        for i in range(2):
            await client1.post(
                "/api/v1/auth/login",
                json={"email": "restart-lockout-test@example.com", "password": f"wrong-{i}"},
            )
        locked = await client1.post(
            "/api/v1/auth/login",
            json={"email": "restart-lockout-test@example.com", "password": "whatever"},
        )
        assert locked.status_code == 429
        assert locked.json()["code"] == "too_many_login_attempts"
        await client1.aclose()
        await manager1.__aexit__(None, None, None)

        # "Restart."
        app2, client2, manager2 = await _build_client(monkeypatch, session_factory, **overrides)
        assert app2.state.login_lockout_tracker is not app1.state.login_lockout_tracker

        still_locked = await client2.post(
            "/api/v1/auth/login",
            json={"email": "restart-lockout-test@example.com", "password": "whatever"},
        )
        assert still_locked.status_code == 429
        assert still_locked.json()["code"] == "too_many_login_attempts"
        await client2.aclose()
        await manager2.__aexit__(None, None, None)
