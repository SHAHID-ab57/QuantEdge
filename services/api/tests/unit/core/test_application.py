"""`app.application.startup`'s JWT secret and Redis enforcement
(M5-E2-T1, M5-E3-T1), and its `.env` duplicate-key check / automation-
config startup logging (ENV-CONFIG-INTEGRITY).

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
from app.core.env_validation import DuplicateEnvKey


@pytest.fixture(autouse=True)
def _no_real_env_file_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolates every test in this file from whatever is actually in this
    developer's own local `.env` — `_check_env_duplicates` reads that file
    directly off disk by design (ENV-CONFIG-INTEGRITY), which would
    otherwise make every unrelated test here pass or fail depending on
    something no test here is about. `TestEnvDuplicateKeyEnforcement`
    overrides this with its own explicit `find_duplicate_env_keys` stand-in
    per test."""
    monkeypatch.setattr(application_module, "find_duplicate_env_keys", lambda path: [])


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "jwt_secret_key": "a-real-secret",
        "database_url": "",
        "redis_url": "",
        # Read by `_log_automation_config` (ENV-CONFIG-INTEGRITY) — mirrors
        # `app/core/config.py`'s own real defaults, the same convention
        # `tests/unit/runtime/test_runtime.py`'s own `_settings()` already
        # follows.
        "market_data_live": False,
        "orderflow_capture_enabled": True,
        "orderflow_retention_days": 365,
        "candle_sync_enabled": True,
        "prediction_grading_enabled": True,
        "paper_trading_funding_enabled": True,
        "paper_trading_strategy_scheduler_enabled": True,
        "retraining_scheduler_enabled": True,
        "retraining_experiment_ids": "",
        "news_sync_enabled": True,
        "external_data_sync_enabled": True,
    }
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


@pytest.mark.asyncio
class TestRedisStartupEnforcement:
    """Follows `database_url`'s own precedent, not the JWT secret's:
    unconfigured skips gracefully, configured-but-unreachable *at
    startup* still fails loudly. See `app.core.config.Settings
    .redis_url`'s own docstring and `ARCHITECTURE.md` § "Redis"."""

    async def test_startup_succeeds_with_redis_unconfigured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(application_module, "get_settings", lambda: _settings(redis_url=""))
        monkeypatch.setattr(application_module, "get_engine", lambda: None)
        await startup()  # must not raise

    async def test_startup_raises_when_redis_is_configured_but_unreachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            application_module,
            "get_settings",
            lambda: _settings(redis_url="redis://nonexistent-host:6379/0"),
        )

        async def _unreachable() -> str:
            return "Connection refused"

        monkeypatch.setattr(application_module, "probe_redis", _unreachable)
        with pytest.raises(RuntimeError, match="Redis connection failed"):
            await startup()

    async def test_startup_succeeds_when_redis_is_configured_and_reachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            application_module,
            "get_settings",
            lambda: _settings(redis_url="redis://localhost:6379/0"),
        )
        monkeypatch.setattr(application_module, "get_engine", lambda: None)

        async def _reachable() -> None:
            return None

        monkeypatch.setattr(application_module, "probe_redis", _reachable)
        await startup()  # must not raise

    async def test_the_jwt_check_runs_before_the_redis_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _boom() -> str:
            raise AssertionError("probe_redis should never be reached with no JWT secret")

        monkeypatch.setattr(
            application_module, "get_settings", lambda: _settings(jwt_secret_key="")
        )
        monkeypatch.setattr(application_module, "probe_redis", _boom)
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            await startup()


@pytest.mark.asyncio
class TestEnvDuplicateKeyEnforcement:
    """ENV-CONFIG-INTEGRITY: `startup` refuses to run at all if `.env`
    declares the same key twice with two different values — the exact
    shape of the real incident (`RETRAINING_EXPERIMENT_IDS` silently
    nullified by a later, empty duplicate) this task exists because of.
    A harmless duplicate (identical values) only warns; it must never
    stop the application from starting."""

    async def test_a_conflicting_duplicate_key_fails_startup_before_the_jwt_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            application_module,
            "find_duplicate_env_keys",
            lambda path: [
                DuplicateEnvKey(
                    key="RETRAINING_EXPERIMENT_IDS",
                    occurrences=((95, "49bbf390-d038-4ed7-8b6c-bcd9a30754f8"), (107, "")),
                )
            ],
        )

        # Even a JWT-secret-less settings object never gets read: the
        # duplicate check runs first and refuses to start before anything
        # else is even attempted.
        def _boom() -> None:
            raise AssertionError("get_settings should never be reached")

        monkeypatch.setattr(application_module, "get_settings", _boom)

        with pytest.raises(RuntimeError, match="RETRAINING_EXPERIMENT_IDS"):
            await startup()

    async def test_the_error_names_the_effective_value_and_every_declaration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            application_module,
            "find_duplicate_env_keys",
            lambda path: [
                DuplicateEnvKey(
                    key="RETRAINING_EXPERIMENT_IDS",
                    occurrences=((95, "49bbf390-d038-4ed7-8b6c-bcd9a30754f8"), (107, "")),
                )
            ],
        )
        monkeypatch.setattr(application_module, "get_settings", lambda: _settings())

        with pytest.raises(RuntimeError) as exc_info:
            await startup()

        message = str(exc_info.value)
        assert "line 95" in message
        assert "line 107" in message
        assert "effective value: ''" in message

    async def test_a_harmless_identical_duplicate_only_warns_and_does_not_fail_startup(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(
            application_module,
            "find_duplicate_env_keys",
            lambda path: [
                DuplicateEnvKey(
                    key="ORDERFLOW_CAPTURE_ENABLED", occurrences=((79, "true"), (150, "true"))
                )
            ],
        )
        monkeypatch.setattr(application_module, "get_settings", lambda: _settings())
        monkeypatch.setattr(application_module, "get_engine", lambda: None)

        with caplog.at_level("WARNING", logger="app.application"):
            await startup()  # must not raise

        assert "ORDERFLOW_CAPTURE_ENABLED" in caplog.text
        assert "2 times" in caplog.text


@pytest.mark.asyncio
class TestAutomationConfigStartupLogging:
    """ENV-CONFIG-INTEGRITY: every automation-gating setting's actually-
    resolved value is logged together, in one place, at every startup —
    so a human glancing at the logs sees the real state without needing
    to separately query `Settings`. Proves the log line carries the real
    values (not just that logging happens), and the targeted warning for
    the exact "enabled but empty" shape of the real incident."""

    async def test_every_automation_gating_setting_appears_in_the_startup_log(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(
            application_module,
            "get_settings",
            lambda: _settings(
                market_data_live=True,
                orderflow_retention_days=365,
                retraining_experiment_ids="49bbf390-d038-4ed7-8b6c-bcd9a30754f8",
            ),
        )
        monkeypatch.setattr(application_module, "get_engine", lambda: None)

        with caplog.at_level("INFO", logger="app.application"):
            await startup()

        [log_line] = [r for r in caplog.records if "Automation configuration" in r.message]
        assert "market_data_live=True" in log_line.message
        assert "orderflow_retention_days=365" in log_line.message
        assert "retraining_experiment_ids='49bbf390-d038-4ed7-8b6c-bcd9a30754f8'" in (
            log_line.message
        )

    async def test_an_empty_experiment_ids_while_enabled_gets_its_own_explicit_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The exact shape of the real incident: enabled, but silently
        retraining nothing. This must be visible on its own, not buried
        in the single combined log line above — a reader shouldn't have
        to notice an empty string inside a long line of other settings."""
        monkeypatch.setattr(
            application_module,
            "get_settings",
            lambda: _settings(retraining_scheduler_enabled=True, retraining_experiment_ids=""),
        )
        monkeypatch.setattr(application_module, "get_engine", lambda: None)

        with caplog.at_level("WARNING", logger="app.application"):
            await startup()

        assert "retraining_experiment_ids is empty" in caplog.text
        assert "retraining_scheduler_enabled is true" in caplog.text

    async def test_no_warning_when_experiment_ids_is_set(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(
            application_module,
            "get_settings",
            lambda: _settings(
                retraining_scheduler_enabled=True,
                retraining_experiment_ids="49bbf390-d038-4ed7-8b6c-bcd9a30754f8",
            ),
        )
        monkeypatch.setattr(application_module, "get_engine", lambda: None)

        with caplog.at_level("WARNING", logger="app.application"):
            await startup()

        assert "retraining_experiment_ids is empty" not in caplog.text

    async def test_no_warning_when_the_scheduler_itself_is_disabled(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An empty `retraining_experiment_ids` is entirely expected, not
        a problem, when the scheduler is disabled outright — the warning
        is specifically for "enabled but pointed at nothing", not for
        "off"."""
        monkeypatch.setattr(
            application_module,
            "get_settings",
            lambda: _settings(retraining_scheduler_enabled=False, retraining_experiment_ids=""),
        )
        monkeypatch.setattr(application_module, "get_engine", lambda: None)

        with caplog.at_level("WARNING", logger="app.application"):
            await startup()

        assert "retraining_experiment_ids is empty" not in caplog.text
