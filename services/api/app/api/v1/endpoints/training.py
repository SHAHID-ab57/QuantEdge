"""Machine Learning Training Framework REST endpoints.

CRUD over training jobs, plus lifecycle actions (`run`, `cancel`) and a
model adapter catalogue — the orchestration surface described in
`ARCHITECTURE.md` § "Machine Learning Training Framework". Implements no
real model training; see `app/training/adapters/placeholder.py`.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.config import get_settings
from app.dependencies.training import get_training_job_service
from app.schemas.training import (
    ModelAdapterCatalogResponse,
    TrainingJobCreateRequest,
    TrainingJobListResponse,
    TrainingJobResponse,
)
from app.services.training import TrainingJobService

router = APIRouter(tags=["training"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown training job, experiment, or model adapter",
        "content": {
            "application/json": {
                "examples": {
                    "training_job_not_found": {
                        "summary": "Unknown training job id",
                        "value": {
                            "code": "training_job_not_found",
                            "detail": "Training job 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 not found",
                        },
                    },
                }
            }
        },
    },
    status.HTTP_409_CONFLICT: {
        "description": "The job's current lifecycle status forbids this action",
        "content": {
            "application/json": {
                "examples": {
                    "invalid_training_job_transition": {
                        "summary": "Illegal status transition",
                        "value": {
                            "code": "invalid_training_job_transition",
                            "detail": "Cannot move a training job from 'completed' to 'running'",
                        },
                    },
                }
            }
        },
    },
}

TrainingJobServiceDep = Annotated[TrainingJobService, Depends(get_training_job_service)]
TrainingJobIdPath = Annotated[uuid.UUID, Path(description="Training job id")]


@router.get(
    "/training-jobs/models",
    response_model=ModelAdapterCatalogResponse,
    summary="List registered model adapters",
    description=(
        "The pluggable model adapter catalogue — the framework's one extension point for a "
        "future TensorFlow, PyTorch, or scikit-learn integration. Only 'placeholder' is "
        "registered today; it performs no real training."
    ),
)
async def list_model_adapters(service: TrainingJobServiceDep) -> ModelAdapterCatalogResponse:
    """Return every registered model adapter."""
    return service.list_model_adapters()


@router.post(
    "/training-jobs",
    response_model=TrainingJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new training job",
    description=(
        "Register a new training job against an existing experiment. The job starts in "
        "'pending' status; call POST /training-jobs/{id}/run to execute the pipeline."
    ),
    responses=_ERROR_RESPONSES,
)
async def create_training_job(
    body: TrainingJobCreateRequest, service: TrainingJobServiceDep
) -> TrainingJobResponse:
    """Create a new training job record."""
    return await service.create(body)


@router.get(
    "/training-jobs",
    response_model=TrainingJobListResponse,
    summary="Search, filter, and sort training jobs",
    responses=_ERROR_RESPONSES,
)
async def list_training_jobs(
    service: TrainingJobServiceDep,
    experiment_id: Annotated[
        uuid.UUID | None, Query(description="Only jobs for this experiment")
    ] = None,
    status_filter: Annotated[
        str | None, Query(alias="status", description="Exact job status")
    ] = None,
    model_type: Annotated[str | None, Query(description="Exact model adapter name")] = None,
    sort: Annotated[
        str,
        Query(
            description=(
                "Sort column; one of status, model_type, created_at, updated_at, "
                "started_at, completed_at"
            )
        ),
    ] = "created_at",
    dir: Annotated[str, Query(description="Sort direction; asc or desc")] = "desc",
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=get_settings().training_jobs_max_limit,
            description="Maximum jobs per page",
        ),
    ] = get_settings().training_jobs_default_limit,
    offset: Annotated[int, Query(ge=0, description="Number of jobs to skip")] = 0,
) -> TrainingJobListResponse:
    """Return a page of training jobs matching the given filter/sort criteria."""
    return await service.search(
        experiment_id=experiment_id,
        status_filter=status_filter,
        model_type=model_type,
        sort=sort,
        direction=dir,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/training-jobs/{job_id}",
    response_model=TrainingJobResponse,
    summary="Get one training job",
    description="Return one training job's full record, including its logs.",
    responses=_ERROR_RESPONSES,
)
async def get_training_job(
    job_id: TrainingJobIdPath, service: TrainingJobServiceDep
) -> TrainingJobResponse:
    """Return one training job by id."""
    return await service.get(job_id)


@router.delete(
    "/training-jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a training job",
    description="Permanently delete a training job and its logs. Refuses a running job.",
    responses=_ERROR_RESPONSES,
)
async def delete_training_job(job_id: TrainingJobIdPath, service: TrainingJobServiceDep) -> None:
    """Delete one training job by id."""
    await service.delete(job_id)


@router.post(
    "/training-jobs/{job_id}/run",
    response_model=TrainingJobResponse,
    summary="Execute the training pipeline for a pending job",
    description=(
        "Runs the six-stage placeholder training pipeline synchronously and returns the "
        "job's final state (completed or failed). No worker/queue service exists yet, so "
        "this call blocks for the duration of the run."
    ),
    responses=_ERROR_RESPONSES,
)
async def run_training_job(
    job_id: TrainingJobIdPath, service: TrainingJobServiceDep
) -> TrainingJobResponse:
    """Execute a pending training job's pipeline."""
    return await service.run(job_id)


@router.post(
    "/training-jobs/{job_id}/cancel",
    response_model=TrainingJobResponse,
    summary="Cancel a pending training job",
    responses=_ERROR_RESPONSES,
)
async def cancel_training_job(
    job_id: TrainingJobIdPath, service: TrainingJobServiceDep
) -> TrainingJobResponse:
    """Cancel one training job, if its current status allows it."""
    return await service.cancel(job_id)
