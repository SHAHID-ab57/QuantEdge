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
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.db.engine import dispose_engine, get_engine, probe_database
from app.dependencies.training import cancel_in_flight_training_jobs
from app.runtime import shutdown_runtime, start_runtime

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
    """Initialize the database engine and verify connectivity."""
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
    """Cancel any in-flight training runs, stop the runtime, then dispose the engine.

    `cancel_in_flight_training_jobs` runs first, before anything that uses
    the same database engine is torn down — same ordering principle as
    `Runtime.shutdown` stopping `CandleSyncScheduler` before its own engine
    use ends. See that function's docstring
    (`app/dependencies/training.py`) for the resulting, disclosed
    limitation: a job whose background task was still running is left
    'running' in the database, not cleanly failed.
    """
    await cancel_in_flight_training_jobs()
    await shutdown_runtime()
    await dispose_engine()
    logger.info("API shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router)

    return app
