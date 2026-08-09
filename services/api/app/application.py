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
    logger.info("API startup complete")


async def shutdown() -> None:
    """Dispose the database engine and pooled connections."""
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
