"""`app.application.startup`'s JWT secret enforcement (M5-E2-T1).

Mirrors `tests/unit/db/test_engine.py`'s own convention: monkeypatch
`get_settings` at the module level rather than touching the real,
process-wide `lru_cache`d singleton — this test's whole point is to
exercise a *different* settings value than every other test in this
session relies on (`tests/conftest.py` forces a real `JWT_SECRET_KEY`
into the environment specifically so the cached singleton never has an
empty one), so it must never risk contaminating that cache.
"""

from types import SimpleNamespace

import pytest

import app.application as application_module
from app.application import startup


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {"jwt_secret_key": "a-real-secret", "database_url": ""}
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
class TestJwtSecretStartupEnforcement:
    async def test_startup_raises_when_the_jwt_secret_is_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A real, loud startup failure — not a lazy exception on first
        login attempt. Deliberately departs from this codebase's own
        "missing configuration degrades gracefully" convention (an unset
        `DELTA_API_KEY` or `DATABASE_URL` doesn't fail startup) — see
        `ARCHITECTURE.md` § "Authentication & Audit Trail" → "JWT secret
        startup enforcement" for why."""
        monkeypatch.setattr(
            application_module, "get_settings", lambda: _settings(jwt_secret_key="")
        )
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            await startup()

    async def test_startup_succeeds_with_a_real_secret_and_no_database_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The JWT check doesn't break this platform's own established
        "runs fully DB-less for health/dev scenarios" behavior — a real
        secret plus no database still starts cleanly, just skipping the
        database step exactly as before this task."""
        monkeypatch.setattr(application_module, "get_settings", lambda: _settings(database_url=""))
        monkeypatch.setattr(application_module, "get_engine", lambda: None)
        await startup()  # must not raise

    async def test_the_jwt_check_runs_before_the_database_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unset secret fails startup even when the database is also
        unreachable — the JWT error, not a database error, must be what
        actually surfaces, since it's the cheaper, more fundamental
        misconfiguration."""

        def _boom() -> None:
            raise AssertionError("get_engine should never be reached with no JWT secret")

        monkeypatch.setattr(
            application_module, "get_settings", lambda: _settings(jwt_secret_key="")
        )
        monkeypatch.setattr(application_module, "get_engine", _boom)
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            await startup()
