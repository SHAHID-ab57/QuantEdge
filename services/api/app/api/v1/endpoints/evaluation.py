"""Model Evaluation & Benchmarking Engine REST endpoints.

The metric catalogue (every registered classification/regression metric)
and the benchmark comparison workflow — see `ARCHITECTURE.md` §
"Model Evaluation & Benchmarking Engine". This engine computes nothing new
at request time beyond the comparison itself: every metric value it
compares was already produced during training
(`app/training/adapters/logistic_regression.py`/`linear_regression.py`,
via the shared `app.evaluation.engine.default_engine`).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.config import get_settings
from app.dependencies.evaluation import get_evaluation_service
from app.schemas.evaluation import (
    BenchmarkRequest,
    BenchmarkResponse,
    BenchmarkRunDetailResponse,
    BenchmarkRunListResponse,
    MetricCatalogResponse,
)
from app.services.evaluation import EvaluationService

router = APIRouter(tags=["evaluation"])

_RUN_NOT_FOUND_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown Benchmark History run id",
        "content": {
            "application/json": {
                "examples": {
                    "benchmark_run_not_found": {
                        "summary": "Unknown benchmark run id",
                        "value": {
                            "code": "benchmark_run_not_found",
                            "detail": (
                                "Benchmark run 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 not found"
                            ),
                        },
                    },
                }
            }
        },
    },
}

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        "description": "The benchmark request named nothing to compare",
        "content": {
            "application/json": {
                "examples": {
                    "no_benchmark_target": {
                        "summary": "No dataset_version, target_column, or experiment_ids given",
                        "value": {
                            "code": "no_benchmark_target",
                            "detail": (
                                "Provide at least one of dataset_version, target_column, or "
                                "experiment_ids to compare training jobs"
                            ),
                        },
                    },
                }
            }
        },
    },
    status.HTTP_404_NOT_FOUND: {
        "description": "The benchmark request matched zero completed training jobs",
        "content": {
            "application/json": {
                "examples": {
                    "empty_benchmark": {
                        "summary": "No completed training jobs matched",
                        "value": {
                            "code": "empty_benchmark",
                            "detail": "No completed training jobs matched this benchmark request",
                        },
                    },
                }
            }
        },
    },
}

EvaluationServiceDep = Annotated[EvaluationService, Depends(get_evaluation_service)]


@router.get(
    "/evaluation/metrics",
    response_model=MetricCatalogResponse,
    summary="List every registered evaluation metric",
    description=(
        "The pluggable metric catalogue — the engine's one extension point for a future "
        "metric. Includes both classification metrics (accuracy, precision, recall, f1, "
        "roc_auc) and regression metrics (mae, mse, rmse, r2)."
    ),
)
async def list_metrics(service: EvaluationServiceDep) -> MetricCatalogResponse:
    """Return every registered metric's metadata."""
    return service.list_metrics()


@router.post(
    "/evaluation/benchmark",
    response_model=BenchmarkResponse,
    summary="Compare completed training jobs by their recorded metrics",
    description=(
        "Compare every completed training job matching dataset_version, target_column, "
        "and/or experiment_ids — a read-only comparison over metrics already recorded "
        "during training, never a re-computation. Returns every matched candidate plus "
        "the best-scoring candidate per metric."
    ),
    responses=_ERROR_RESPONSES,
)
async def benchmark(body: BenchmarkRequest, service: EvaluationServiceDep) -> BenchmarkResponse:
    """Compare completed training jobs matching `body`."""
    return await service.benchmark(body)


BenchmarkRunIdPath = Annotated[uuid.UUID, Path(description="Benchmark History run id")]


@router.get(
    "/evaluation/history",
    response_model=BenchmarkRunListResponse,
    summary="List past benchmark comparisons (Benchmark History)",
    description=(
        "Every successful `POST /evaluation/benchmark` call is recorded here, most recent "
        "first by default — metadata only (dataset version, target column, candidate count); "
        "fetch one run's own detail endpoint to reopen its full comparison."
    ),
)
async def list_benchmark_runs(
    service: EvaluationServiceDep,
    dataset_version: Annotated[
        str | None, Query(description="Only runs made with this dataset_version")
    ] = None,
    target_column: Annotated[
        str | None, Query(description="Only runs made with this target_column")
    ] = None,
    sort: Annotated[
        str,
        Query(
            description=(
                "Sort column; one of dataset_version, target_column, candidate_count, created_at"
            )
        ),
    ] = "created_at",
    dir: Annotated[str, Query(description="Sort direction; asc or desc")] = "desc",
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=get_settings().evaluation_history_max_limit,
            description="Maximum runs per page",
        ),
    ] = get_settings().evaluation_history_default_limit,
    offset: Annotated[int, Query(ge=0, description="Number of runs to skip")] = 0,
) -> BenchmarkRunListResponse:
    """Return a page of past benchmark runs matching the given filter/sort criteria."""
    return await service.list_benchmark_runs(
        dataset_version=dataset_version,
        target_column=target_column,
        sort=sort,
        direction=dir,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/evaluation/history/{run_id}",
    response_model=BenchmarkRunDetailResponse,
    summary="Reopen one past benchmark comparison",
    description=(
        "Return one persisted run's full record — the exact request and response it produced."
    ),
    responses=_RUN_NOT_FOUND_RESPONSES,
)
async def get_benchmark_run(
    run_id: BenchmarkRunIdPath, service: EvaluationServiceDep
) -> BenchmarkRunDetailResponse:
    """Return one persisted benchmark run by id."""
    return await service.get_benchmark_run(run_id)


@router.delete(
    "/evaluation/history/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove one past run from Benchmark History",
    description="Deletes the persisted record only — never touches the underlying training jobs.",
    responses=_RUN_NOT_FOUND_RESPONSES,
)
async def delete_benchmark_run(run_id: BenchmarkRunIdPath, service: EvaluationServiceDep) -> None:
    """Delete one persisted benchmark run by id."""
    await service.delete_benchmark_run(run_id)
