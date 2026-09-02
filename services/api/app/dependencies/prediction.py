"""Dependency providers for the Live Prediction Service API."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.dependencies.features import get_dataset_builder
from app.dependencies.ml_datasets import get_target_pipeline
from app.dependencies.training import get_training_job_service
from app.evaluation.metrics import load_builtin_metrics
from app.evaluation.registry import default_registry as default_metric_registry
from app.prediction.engine import default_engine
from app.repositories.candles import CandleRepository
from app.repositories.experiments import ExperimentRepository
from app.repositories.markets import MarketRepository
from app.repositories.predictions import PredictionRepository
from app.services.experiments import ExperimentService
from app.services.features import FeatureService
from app.services.prediction import PredictionService


def get_prediction_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PredictionService:
    """Build the prediction service wired to the request session.

    Composes `TrainingJobService`/`ExperimentService`/`FeatureService`
    directly (never a second copy of any of them) — the same reuse
    `get_evaluation_service` already established for a service layered over
    an existing one. `FeatureService` is built exactly the way
    `get_feature_service` (`app/dependencies/features.py`) builds it, so a
    live prediction's feature reconstruction shares the process-wide
    pipeline/cache every other feature consumer already warms.

    `target_pipeline`/`metric_registry` back `grade_pending` (prediction
    grading, not live inference): `get_target_pipeline()` is the *exact*
    process-wide pipeline the ML Dataset Builder itself uses to generate
    training labels (`app/dependencies/ml_datasets.py`), and
    `default_metric_registry` (with `load_builtin_metrics()` called
    explicitly, the same pattern `get_evaluation_service` already uses for
    its own registry) is the same one `EvaluationEngine` reads `accuracy`/
    `mae` from — neither is a second copy built for grading alone.
    """
    settings = get_settings()
    load_builtin_metrics()
    return PredictionService(
        repository=PredictionRepository(session),
        training_job_service=get_training_job_service(session),
        experiment_service=ExperimentService(repository=ExperimentRepository(session)),
        feature_service=FeatureService(
            candle_repository=CandleRepository(session),
            market_repository=MarketRepository(session),
            builder=get_dataset_builder(),
            default_limit=settings.candles_default_limit,
            max_limit=settings.candles_max_limit,
        ),
        market_repository=MarketRepository(session),
        candle_repository=CandleRepository(session),
        engine=default_engine,
        target_pipeline=get_target_pipeline(),
        metric_registry=default_metric_registry,
    )
