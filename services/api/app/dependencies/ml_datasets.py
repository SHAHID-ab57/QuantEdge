"""Dependency providers for the ML Dataset Builder API."""

import functools
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.dependencies.dataset_validation import get_dataset_validator
from app.dependencies.features import get_dataset_builder
from app.ml_datasets.dataset import MLDatasetBuilder
from app.ml_datasets.pipeline import TargetPipeline
from app.ml_datasets.registry import default_registry as default_target_registry
from app.ml_datasets.split import ChronologicalSplitter
from app.ml_datasets.targets import load_builtin_targets
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.ml_dataset_builds import MLDatasetBuildRepository
from app.services.ml_datasets import MLDatasetService


@functools.lru_cache(maxsize=1)
def get_target_pipeline() -> TargetPipeline:
    """Return the process-wide target pipeline."""
    load_builtin_targets()
    return TargetPipeline(default_target_registry)


@functools.lru_cache(maxsize=1)
def get_ml_dataset_builder() -> MLDatasetBuilder:
    """Return the process-wide ML dataset builder.

    Both ``feature_builder`` and ``validator`` are the *exact same*
    instances `/features/dataset` and `/validation` already use
    (`get_dataset_builder`/`get_dataset_validator`) — never a second
    instance wrapping the same underlying registry. There is only ever one
    feature-building path and one validation engine on this platform; the
    ML Dataset Builder composes both rather than re-deriving either.
    """
    return MLDatasetBuilder(
        feature_builder=get_dataset_builder(),
        target_pipeline=get_target_pipeline(),
        validator=get_dataset_validator(),
        splitter=ChronologicalSplitter(),
    )


def get_ml_dataset_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MLDatasetService:
    """Build the ML dataset service wired to the request session."""
    settings = get_settings()
    return MLDatasetService(
        candle_repository=CandleRepository(session),
        market_repository=MarketRepository(session),
        builder=get_ml_dataset_builder(),
        default_limit=settings.candles_default_limit,
        max_limit=settings.candles_max_limit,
        build_repository=MLDatasetBuildRepository(session),
        history_default_limit=settings.ml_dataset_builds_default_limit,
        history_max_limit=settings.ml_dataset_builds_max_limit,
    )
