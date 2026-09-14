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
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.redis import dispose_redis_client, get_redis_client, probe_redis
from app.db.engine import dispose_engine, get_engine, probe_database
from app.middleware.rate_limit import RateLimitMiddleware, build_rate_limiter
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


async def startup() -> None:
    """Enforce the JWT secret, verify Redis (if configured), then
    initialize the database engine and verify connectivity.

    The JWT secret check runs first, and unconditionally — before either
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
    settings = get_settings()
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

    register_exception_handlers(app)
    app.include_router(api_router)

    return app
