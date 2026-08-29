"""Dependency providers for the Model Evaluation & Benchmarking Engine API."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.evaluation.registry import default_registry as default_metric_registry
from app.repositories.evaluation_benchmark_runs import EvaluationBenchmarkRunRepository
from app.repositories.experiments import ExperimentRepository
from app.repositories.training import TrainingJobRepository
from app.services.evaluation import EvaluationService
from app.services.experiments import ExperimentService
from app.training.adapters import load_builtin_model_adapters
from app.training.registry import default_registry as default_model_adapter_registry


def get_evaluation_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> EvaluationService:
    """Build the evaluation service wired to the request session.

    Composes `ExperimentService` directly (not a second copy of it), the
    same reuse `get_training_job_service` already established — a
    benchmark's experiment names come from the exact same service
    `/experiments` itself calls, never a second lookup path.
    """
    load_builtin_model_adapters()
    settings = get_settings()
    return EvaluationService(
        training_repository=TrainingJobRepository(session),
        experiment_service=ExperimentService(repository=ExperimentRepository(session)),
        metric_registry=default_metric_registry,
        model_adapter_registry=default_model_adapter_registry,
        benchmark_run_repository=EvaluationBenchmarkRunRepository(session),
        benchmark_max_candidates=settings.evaluation_benchmark_max_candidates,
        history_default_limit=settings.evaluation_history_default_limit,
        history_max_limit=settings.evaluation_history_max_limit,
    )
