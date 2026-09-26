"""Application factory.

Assembles the FastAPI application: configuration, logging, lifespan,
middleware, exception handlers, and versioned routers.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.auth.login_lockout import build_login_lockout_tracker
from app.auth.token_revocation import build_token_blocklist
from app.core.config import Settings, get_settings
from app.core.env_validation import find_duplicate_env_keys
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.redis import dispose_redis_client, get_redis_client, probe_redis
from app.db.engine import dispose_engine, get_engine, probe_database
from app.middleware.rate_limit import RateLimitMiddleware, build_rate_limiter
from app.middleware.request_context import RequestContextMiddleware
from app.monitoring.error_tracking import init_error_tracking
from app.runtime import shutdown_runtime, start_runtime
from app.services import background_tasks

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle."""
    setup_logging()

    await startup()
    try:
        yield
    finally:
        await shutdown()


def _check_env_duplicates() -> None:
    """ENV-CONFIG-INTEGRITY: fails the whole application at startup if
    the real, local `.env` file declares the same key twice with two
    different values — a conflicting duplicate is refused exactly like a
    missing JWT secret, before anything else runs. A harmless duplicate
    (identical values on every declaration) only logs a warning.

    `python-dotenv` (what `Settings`' own `env_file` loading uses)
    resolves a duplicate key to its *last* declaration, silently — no
    error, no warning, nothing. `RETRAINING_EXPERIMENT_IDS` sat silently
    nullified this exact way for an unknown number of days: a real
    lineage ID declared once, then re-declared empty later in the same
    file, with the scheduler ticking on schedule and retraining nothing
    the entire time.

    **Startup, not CI, is the mechanism that actually catches this.**
    `.env` is gitignored and per-environment (`configs/README.md`) — a
    CI check only ever sees what's committed, so it could check
    `.env.example` (see `scripts/check_env_duplicates.py`, run in CI)
    but can never see the real file where this incident happened at all.
    Only a check that runs where `.env` actually lives — here, at the
    startup of the process that reads it — closes this gap for real.
    """
    conflicting: list[str] = []
    for duplicate in find_duplicate_env_keys(".env"):
        if duplicate.values_differ:
            declarations = ", ".join(
                f"line {line_number}={value!r}" for line_number, value in duplicate.occurrences
            )
            conflicting.append(
                f"{duplicate.key} ({declarations}; effective value: {duplicate.effective_value!r})"
            )
        else:
            logger.warning(
                "%s is declared %d times in .env with the identical value — harmless, "
                "but worth removing the redundant line(s)",
                duplicate.key,
                len(duplicate.occurrences),
            )
    if conflicting:
        raise RuntimeError(
            "Conflicting duplicate keys in .env (ENV-CONFIG-INTEGRITY): "
            + "; ".join(conflicting)
            + ". python-dotenv silently resolves each to its LAST declaration — this "
            "is exactly how RETRAINING_EXPERIMENT_IDS sat nullified with no error "
            "anywhere. Remove the redundant declaration(s) before starting."
        )


def _log_automation_config(settings: Settings) -> None:
    """ENV-CONFIG-INTEGRITY: every setting that gates a scheduler or
    automation loop, logged together in one place at startup, so a human
    glancing at the startup logs can see the actually-resolved values
    directly — never needing to separately query `Settings` or hunt
    across several different schedulers' own, separately-logged
    "started" lines to find out. Complements, never replaces, each
    scheduler's own descriptive startup log line (e.g. `OrderFlowCapture`
    already logs its own resolved `retention=365d`).
    """
    logger.info(
        "Automation configuration: market_data_live=%s orderflow_capture_enabled=%s "
        "orderflow_retention_days=%s candle_sync_enabled=%s "
        "prediction_grading_enabled=%s paper_trading_funding_enabled=%s "
        "paper_trading_strategy_scheduler_enabled=%s retraining_scheduler_enabled=%s "
        "retraining_experiment_ids=%r news_sync_enabled=%s external_data_sync_enabled=%s",
        settings.market_data_live,
        settings.orderflow_capture_enabled,
        settings.orderflow_retention_days,
        settings.candle_sync_enabled,
        settings.prediction_grading_enabled,
        settings.paper_trading_funding_enabled,
        settings.paper_trading_strategy_scheduler_enabled,
        settings.retraining_scheduler_enabled,
        settings.retraining_experiment_ids,
        settings.news_sync_enabled,
        settings.external_data_sync_enabled,
    )
    # The exact shape of the incident this task exists to catch: enabled,
    # but silently retraining nothing. Called out explicitly rather than
    # left for a reader to notice buried in the line above.
    if settings.retraining_scheduler_enabled and not settings.retraining_experiment_ids.strip():
        logger.warning(
            "retraining_experiment_ids is empty while retraining_scheduler_enabled is "
            "true: the scheduler will tick on schedule but retrain no lineage at all. "
            "If a lineage was intended, check .env for a duplicate/overriding "
            "declaration (ENV-CONFIG-INTEGRITY)."
        )


async def startup() -> None:
    """Check `.env` for conflicting duplicate keys, log every automation-
    gating setting's resolved value, enforce the JWT secret, verify Redis
    (if configured), then initialize the database engine and verify
    connectivity.

    The `.env` duplicate check and the automation-config log both run
    first, and unconditionally — before the JWT secret check itself —
    since they are cheap, require no I/O, and a config problem should be
    visible (or fatal) before anything else about startup is even
    attempted (see `_check_env_duplicates`/`_log_automation_config`'s own
    docstrings for why, ENV-CONFIG-INTEGRITY).

    The JWT secret check runs next, and unconditionally — before either
    the Redis or the database check, and regardless of whether either is
    even configured — because it is cheap, requires no I/O, and this
    application should never be reachable at all without a real signing
    secret configured. See `app.core.config.Settings.jwt_secret_key`'s
    own docstring, and `ARCHITECTURE.md` § "Authentication & Audit
    Trail" → "JWT secret startup enforcement", for why this deliberately
    departs from every other configuration value in this file (an unset
    `DELTA_API_KEY` or `DATABASE_URL` degrades gracefully instead).

    Redis (M5-E3-T1) follows `database_url`'s own precedent exactly, not
    the JWT secret's: unconfigured skips gracefully (rate limiting,
    login lockout, and token revocation all fall back to their
    in-process equivalents — see `app.core.config.Settings.redis_url`'s
    own docstring for the full reasoning); configured but unreachable
    *at startup* still fails loudly, the same as a configured-but-
    unreachable database, since a deployment that declared it wants
    Redis-backed durability should not silently fall back to a weaker
    guarantee without an operator finding out.
    """
    _check_env_duplicates()
    settings = get_settings()
    _log_automation_config(settings)
    if not settings.jwt_secret_key:
        raise RuntimeError(
            "JWT_SECRET_KEY is not configured. This service cannot start without a "
            "real JWT signing secret — set JWT_SECRET_KEY to a long, random value "
            "before running it. (Deliberate: unlike a missing DELTA_API_KEY or "
            "DATABASE_URL, which degrade gracefully, a missing authentication "
            "secret fails the whole application at startup — see ARCHITECTURE.md "
            "§ 'Authentication & Audit Trail' → 'JWT secret startup enforcement'.)"
        )

    if not settings.redis_url:
        logger.info(
            "Redis not configured; rate limiting, login lockout, and token "
            "revocation use their in-process fallbacks"
        )
    else:
        logger.info("Verifying Redis connection...")
        redis_error = await probe_redis()
        if redis_error is not None:
            logger.error("Redis connection failed: %s", redis_error)
            raise RuntimeError(f"Redis connection failed: {redis_error}")
        logger.info("Redis connection established")

    if get_engine() is None:
        logger.warning("Skipping database startup: database URL not configured")
        logger.info("API startup complete")
        return

    logger.info("Verifying database connection...")
    error = await probe_database()
    if error is not None:
        logger.error("Database connection failed: %s", error)
        raise RuntimeError(f"Database connection failed: {error}")
    logger.info("Database connection established")
    await start_runtime()
    logger.info("API startup complete")


async def shutdown() -> None:
    """Cancel any in-flight background tasks, stop the runtime, dispose the engine.

    `background_tasks.cancel_all()` runs first, before anything that uses
    the same database engine is torn down — same ordering principle as
    `Runtime.shutdown` stopping `CandleSyncScheduler` before its own engine
    use ends. Cancels every in-flight training run *and* backtest alike —
    one shared registry, one shutdown path (see
    `app/services/background_tasks.py`'s own docstring for the resulting,
    disclosed limitation: a job whose background task was still running is
    left however the crash found it, not cleanly failed).
    """
    await background_tasks.cancel_all()
    await shutdown_runtime()
    await dispose_engine()
    await dispose_redis_client()
    logger.info("API shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    # Before the app object exists, deliberately: the SDK's Starlette
    # integration hooks the middleware stack, which Starlette builds on
    # the first ASGI call — earlier than the lifespan, where a call like
    # `setup_logging()` can safely live.
    init_error_tracking(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    # Rate limiting (M5-E2-T1), login lockout, and token revocation
    # (M5-E3-T1) all live on `app.state` — created fresh here, per
    # `create_app()` call, rather than as module-level singletons, so the
    # many independent app instances this test suite creates never share
    # state with each other. Each is Redis-backed when `REDIS_URL` is
    # configured (`redis_client` below is non-`None`), else the
    # in-process fallback — see `app.middleware.rate_limit`,
    # `app.auth.login_lockout`, and `app.auth.token_revocation`'s own
    # module docstrings, and `ARCHITECTURE.md` § "Redis", for the full
    # reasoning.
    redis_client = get_redis_client()
    app.state.rate_limiter = build_rate_limiter(redis_client, settings)
    app.state.login_lockout_tracker = build_login_lockout_tracker(
        redis_client,
        max_attempts=settings.login_lockout_max_attempts,
        window_seconds=settings.login_lockout_window_seconds,
        cooldown_seconds=settings.login_lockout_cooldown_seconds,
    )
    app.state.token_blocklist = build_token_blocklist(redis_client)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware, settings=settings)
    # Added last, so it is the outermost: everything below (rate limiting,
    # handlers, routes) runs with the request id bound.
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router)

    return app
