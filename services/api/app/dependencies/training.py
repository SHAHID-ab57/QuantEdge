"""Dependency providers for the Machine Learning Training Framework API."""

import functools
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.experiments import ExperimentRepository
from app.repositories.training import TrainingJobRepository
from app.services.experiments import ExperimentService
from app.services.training import TrainingJobService
from app.training.adapters import load_builtin_model_adapters
from app.training.pipeline import TrainingPipeline
from app.training.registry import default_registry as default_model_adapter_registry


@functools.lru_cache(maxsize=1)
def get_training_pipeline() -> TrainingPipeline:
    """Return the process-wide training pipeline."""
    load_builtin_model_adapters()
    return TrainingPipeline(default_model_adapter_registry)


def get_training_job_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TrainingJobService:
    """Build the training job service wired to the request session.

    Composes `ExperimentService` directly (not a second copy of it) so the
    "update experiment" pipeline stage reuses the exact same experiment
    mutation logic `/experiments` itself calls — see
    `app/services/training.py`'s module docstring.
    """
    return TrainingJobService(
        repository=TrainingJobRepository(session),
        experiment_service=ExperimentService(repository=ExperimentRepository(session)),
        pipeline=get_training_pipeline(),
    )
