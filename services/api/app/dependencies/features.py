"""Dependency providers for the feature engineering API."""

import functools
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.dependencies.indicators import get_indicator_engine
from app.features.builtin import load_builtin_features
from app.features.cache import FeatureCache
from app.features.dataset import FeatureDatasetBuilder
from app.features.pipeline import FeaturePipeline
from app.features.registry import default_registry
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.services.features import FeatureService


@functools.lru_cache(maxsize=1)
def get_feature_pipeline() -> FeaturePipeline:
    """Return the process-wide feature pipeline.

    Cached because the registry is meant to be shared: rebuilding it per
    request would re-run discovery on every call. The pipeline holds no
    request-scoped state — generators are stateless — so one instance
    safely serves every request.

    Builtin generators are loaded against the *same* ``IndicatorEngine``
    the indicator API uses, so the moving-average features delegate to an
    engine whose result cache is already warm from chart and overlay
    traffic rather than to a second, cold one. The pipeline itself is given
    its own process-wide ``FeatureCache`` (see ``app/features/cache.py``) —
    a second, independently-bounded cache at the same per-generator
    granularity, which is what lets ``ohlcv``/``candle_shape`` (not
    indicator-backed) benefit from a repeated identical request too.
    """
    load_builtin_features(engine=get_indicator_engine())
    return FeaturePipeline(default_registry, FeatureCache())


@functools.lru_cache(maxsize=1)
def get_dataset_builder() -> FeatureDatasetBuilder:
    """Return the process-wide dataset builder."""
    return FeatureDatasetBuilder(get_feature_pipeline())


def get_feature_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FeatureService:
    """Build the feature service wired to the request session."""
    settings = get_settings()
    return FeatureService(
        candle_repository=CandleRepository(session),
        market_repository=MarketRepository(session),
        builder=get_dataset_builder(),
        default_limit=settings.candles_default_limit,
        max_limit=settings.candles_max_limit,
    )
