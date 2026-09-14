"""End-to-end proof that `RateLimitMiddleware` (M5-E2-T1) actually rejects
requests through the real ASGI stack, not just that `TokenBucketRateLimiter`
itself works in isolation (see `tests/unit/middleware/test_rate_limit.py`
for that).

Builds its own app (rather than using the shared `tests/conftest.py`
fixtures) with a monkeypatched `get_settings` giving a deliberately tiny
`rate_limit_requests`, so a handful of real requests — not 120 — is
enough to trigger a real `429` without waiting a real minute. `get_db`
is still overridden onto the shared in-memory test engine (exactly like
the root `app` fixture does) so an authenticated request can genuinely
resolve a real user rather than 500ing on an unconfigured database.
"""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

import app.application as application_module
from app.auth.security import create_access_token
from app.core.config import Settings
from app.db.session import get_db
from tests.conftest import SessionFactory

_SETTINGS_KWARGS: dict[str, object] = {
    "jwt_secret_key": "rate-limit-test-only-secret-not-used-elsewhere",
    "database_url": "",
    "rate_limit_requests": 3,
    "rate_limit_window_seconds": 60,
}


def _settings() -> Settings:
    return Settings(**_SETTINGS_KWARGS)  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def rate_limited_client(
    monkeypatch: pytest.MonkeyPatch, session_factory: SessionFactory
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setattr(application_module, "get_settings", _settings)
    app: FastAPI = application_module.create_app()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
class TestGeneralRateLimiting:
    async def test_requests_within_capacity_all_succeed(
        self, rate_limited_client: httpx.AsyncClient
    ) -> None:
        for _ in range(3):
            response = await rate_limited_client.post(
                "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
            )
            assert response.status_code == 401  # rejected on credentials, not rate-limited

    async def test_exceeding_capacity_returns_429_with_retry_after(
        self, rate_limited_client: httpx.AsyncClient
    ) -> None:
        for _ in range(3):
            await rate_limited_client.post(
                "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
            )
        response = await rate_limited_client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
        )
        assert response.status_code == 429
        assert response.json()["code"] == "rate_limited"
        assert "Retry-After" in response.headers

    async def test_liveness_endpoints_are_exempt_from_rate_limiting(
        self, rate_limited_client: httpx.AsyncClient
    ) -> None:
        """Orchestration/monitoring health probes must never be throttled —
        confirmed by exceeding the tiny capacity via login first, then
        proving `/health` still gets a real answer (503, since this test
        app has no database configured — a liveness fact, not a
        rate-limit rejection) rather than a 429."""
        for _ in range(4):
            await rate_limited_client.post(
                "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
            )
        response = await rate_limited_client.get("/health")
        assert response.status_code != 429

    async def test_an_authenticated_users_requests_are_tracked_by_user_id_not_shared_ip(
        self, rate_limited_client: httpx.AsyncClient
    ) -> None:
        """`_resolve_key` prefers a valid bearer token's own subject over
        the client IP — proven here by exhausting the anonymous (IP-keyed)
        bucket first, then showing an authenticated request still goes
        through on the very same connection/IP."""
        token = create_access_token(user_id=uuid.uuid4(), settings=_settings())

        for _ in range(3):
            await rate_limited_client.post(
                "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
            )
        exhausted = await rate_limited_client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
        )
        assert exhausted.status_code == 429  # the anonymous/IP bucket is now empty

        # A real 401 (the token names no real user), but crucially *not*
        # a 429 — this authenticated request was never charged against
        # the already-exhausted anonymous bucket, because it has its own.
        response = await rate_limited_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_token"  # not "rate_limited"
