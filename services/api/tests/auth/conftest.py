"""Fixtures for `tests/auth/` — the one suite that must NOT use the root
`app`/`client` fixtures' global `get_current_user` override.

`tests/conftest.py`'s shared `app` fixture overrides `get_current_user` to
return a fixed `test_user` for every other test file, so the ~150
pre-existing endpoint tests written before authentication existed keep
exercising the behavior they actually test. That override is exactly the
boundary this suite exists to prove, so it can't be reused here — these
fixtures rebuild `app`/`client` with a *real* `get_current_user`, wired to
a real JWT secret (`get_settings` is overridden instead of relying on the
process-wide, `lru_cache`d `Settings()` singleton or environment variables,
so this suite's secret can never leak into, or be affected by, any other
test module).
"""

from collections.abc import AsyncIterator, Generator

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import create_app
from app.auth.security import create_access_token, hash_password
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import User
from tests.conftest import SessionFactory

#: A real, fixed secret used only by this suite's own overridden
#: `get_settings` — never read from the environment or the process-wide
#: `Settings()` singleton, so it can't leak into or be affected by any
#: other test module's own settings.
TEST_JWT_SECRET = "tests-auth-suite-only-secret-never-used-outside-tests"  # noqa: S105


def _test_settings() -> Settings:
    return Settings(
        jwt_secret_key=TEST_JWT_SECRET,
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=60,
    )


@pytest.fixture
def app(session_factory: SessionFactory) -> Generator[FastAPI]:
    """A real app with a real `get_current_user` — no auth bypass.

    Only `get_db` (the shared in-memory test engine) and `get_settings`
    (a real JWT secret) are overridden; `get_current_user` runs exactly
    as it does in production.
    """
    app = create_app()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = _test_settings
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client exercising the real app through the ASGI interface."""
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
            yield test_client


@pytest_asyncio.fixture
async def registered_user(session_factory: SessionFactory) -> User:
    """A real, persisted user with a known plaintext password, for login tests."""
    async with session_factory() as session:
        user = User(
            email="auth-suite-user@example.com",
            hashed_password=hash_password("correct-horse-battery-staple"),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
def auth_token(registered_user: User) -> str:
    """A real, valid bearer token for `registered_user`, signed with this
    suite's own `_test_settings()` — the same settings `app`'s overridden
    `get_settings` hands to `get_current_user` at request time."""
    return create_access_token(user_id=registered_user.id, settings=_test_settings())


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    """`Authorization` header carrying a real, valid bearer token."""
    return {"Authorization": f"Bearer {auth_token}"}
