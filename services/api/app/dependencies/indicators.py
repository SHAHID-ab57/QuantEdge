"""Dependency providers for the indicator API."""

import functools
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.indicators.builtin import load_builtin_indicators
from app.indicators.cache import IndicatorCache
from app.indicators.engine import IndicatorEngine
from app.indicators.registry import default_registry
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.services.indicators import IndicatorService


@functools.lru_cache(maxsize=1)
def get_indicator_engine() -> IndicatorEngine:
    """Return the process-wide indicator engine.

    Cached because both the registry and the result cache are meant to be
    shared: rebuilding the engine per request would discard every cached
    result and re-run discovery on every call. The engine holds no
    request-scoped state — indicators are stateless and the cache is keyed
    by content — so one instance safely serves every request.
    """
    load_builtin_indicators()
    return IndicatorEngine(default_registry, IndicatorCache())


def get_indicator_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> IndicatorService:
    """Build the indicator service wired to the request session."""
    settings = get_settings()
    return IndicatorService(
        candle_repository=CandleRepository(session),
        market_repository=MarketRepository(session),
        engine=get_indicator_engine(),
        default_limit=settings.candles_default_limit,
        max_limit=settings.candles_max_limit,
    )
