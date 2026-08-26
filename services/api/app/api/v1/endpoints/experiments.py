"""Experiment Management REST endpoints.

Full CRUD over experiments, plus nested create/delete for their metrics
and artifact references — the platform's one registry for "what was
tried, over which dataset, with what configuration, and what happened."
See `ARCHITECTURE.md` § "Experiment Management System" for the full design.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.config import get_settings
from app.dependencies.experiments import get_experiment_service
from app.schemas.experiments import (
    ArtifactCreateRequest,
    ArtifactDTO,
    ExperimentCreateRequest,
    ExperimentListResponse,
    ExperimentResponse,
    ExperimentUpdateRequest,
    MetricCreateRequest,
    MetricDTO,
)
from app.services.experiments import ExperimentService

router = APIRouter(tags=["experiments"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown experiment, metric, or artifact id",
        "content": {
            "application/json": {
                "examples": {
                    "experiment_not_found": {
                        "summary": "Unknown experiment id",
                        "value": {
                            "code": "experiment_not_found",
                            "detail": "Experiment 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 not found",
                        },
                    },
                }
            }
        },
    },
    status.HTTP_400_BAD_REQUEST: {
        "description": "Invalid sort column or direction",
        "content": {
            "application/json": {
                "examples": {
                    "invalid_sort": {
                        "summary": "Unknown sort column",
                        "value": {
                            "code": "invalid_sort",
                            "detail": (
                                "Unsupported sort 'score' (direction 'asc'); supported "
                                "columns: created_at, model_type, name, status, updated_at, "
                                "directions: asc, desc"
                            ),
                        },
                    },
                }
            }
        },
    },
}

ExperimentServiceDep = Annotated[ExperimentService, Depends(get_experiment_service)]
ExperimentIdPath = Annotated[uuid.UUID, Path(description="Experiment id")]


@router.post(
    "/experiments",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new experiment",
    description=(
        "Record a new experiment: its dataset version, feature set, target configuration, "
        "split configuration, a placeholder model type, status, notes, and tags. Recording "
        "an experiment never builds or trains anything — it is a registry entry a researcher "
        "fills in around a build/train they ran (or are about to run) elsewhere."
    ),
)
async def create_experiment(
    body: ExperimentCreateRequest, service: ExperimentServiceDep
) -> ExperimentResponse:
    """Create a new experiment record."""
    return await service.create(body)


@router.get(
    "/experiments",
    response_model=ExperimentListResponse,
    summary="Search, filter, and sort experiments",
    description=(
        "Return one page of experiments. `q` searches name and notes (case-insensitive "
        "substring). `status`, `model_type`, `dataset_version`, and `tag` each narrow the "
        "result to an exact match. Results are sorted by a whitelisted column."
    ),
    responses=_ERROR_RESPONSES,
)
async def list_experiments(
    service: ExperimentServiceDep,
    q: Annotated[
        str | None, Query(description="Case-insensitive substring search over name and notes")
    ] = None,
    status_filter: Annotated[
        str | None, Query(alias="status", description="Exact experiment status")
    ] = None,
    model_type: Annotated[str | None, Query(description="Exact model type")] = None,
    dataset_version: Annotated[str | None, Query(description="Exact dataset version")] = None,
    tag: Annotated[str | None, Query(description="Exact tag")] = None,
    sort: Annotated[
        str,
        Query(description="Sort column; one of name, status, model_type, created_at, updated_at"),
    ] = "created_at",
    dir: Annotated[str, Query(description="Sort direction; asc or desc")] = "desc",
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=get_settings().experiments_max_limit,
            description="Maximum experiments per page",
        ),
    ] = get_settings().experiments_default_limit,
    offset: Annotated[int, Query(ge=0, description="Number of experiments to skip")] = 0,
) -> ExperimentListResponse:
    """Return a page of experiments matching the given search/filter/sort criteria."""
    return await service.search(
        search=q,
        status_filter=status_filter,
        model_type=model_type,
        dataset_version=dataset_version,
        tag=tag,
        sort=sort,
        direction=dir,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/experiments/{experiment_id}",
    response_model=ExperimentResponse,
    summary="Get one experiment",
    description="Return one experiment's full record, including its metrics and artifacts.",
    responses=_ERROR_RESPONSES,
)
async def get_experiment(
    experiment_id: ExperimentIdPath, service: ExperimentServiceDep
) -> ExperimentResponse:
    """Return one experiment by id."""
    return await service.get(experiment_id)


@router.patch(
    "/experiments/{experiment_id}",
    response_model=ExperimentResponse,
    summary="Update an experiment",
    description=(
        "Partially update an experiment — only fields present in the request body are "
        "changed. Sending `tags` replaces the full tag set; omitting it leaves tags untouched."
    ),
    responses=_ERROR_RESPONSES,
)
async def update_experiment(
    experiment_id: ExperimentIdPath,
    body: ExperimentUpdateRequest,
    service: ExperimentServiceDep,
) -> ExperimentResponse:
    """Apply a partial update to one experiment."""
    return await service.update(experiment_id, body)


@router.delete(
    "/experiments/{experiment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an experiment",
    description="Permanently delete an experiment and its metrics and artifact references.",
    responses=_ERROR_RESPONSES,
)
async def delete_experiment(experiment_id: ExperimentIdPath, service: ExperimentServiceDep) -> None:
    """Delete one experiment by id."""
    await service.delete(experiment_id)


@router.post(
    "/experiments/{experiment_id}/metrics",
    response_model=MetricDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Record a metric against an experiment",
    responses=_ERROR_RESPONSES,
)
async def create_metric(
    experiment_id: ExperimentIdPath,
    body: MetricCreateRequest,
    service: ExperimentServiceDep,
) -> MetricDTO:
    """Record one evaluation metric against an experiment."""
    return await service.add_metric(experiment_id, body)


@router.delete(
    "/experiments/{experiment_id}/metrics/{metric_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a metric",
    responses=_ERROR_RESPONSES,
)
async def delete_metric(
    experiment_id: ExperimentIdPath,
    metric_id: Annotated[uuid.UUID, Path(description="Metric id")],
    service: ExperimentServiceDep,
) -> None:
    """Delete one metric from an experiment."""
    await service.delete_metric(experiment_id, metric_id)


@router.post(
    "/experiments/{experiment_id}/artifacts",
    response_model=ArtifactDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Record an artifact reference against an experiment",
    description=(
        "Record a *reference* to an artifact (a file path, export filename, or URL) — this "
        "platform does not store artifact content, only the pointer to it."
    ),
    responses=_ERROR_RESPONSES,
)
async def create_artifact(
    experiment_id: ExperimentIdPath,
    body: ArtifactCreateRequest,
    service: ExperimentServiceDep,
) -> ArtifactDTO:
    """Record one artifact reference against an experiment."""
    return await service.add_artifact(experiment_id, body)


@router.delete(
    "/experiments/{experiment_id}/artifacts/{artifact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an artifact reference",
    responses=_ERROR_RESPONSES,
)
async def delete_artifact(
    experiment_id: ExperimentIdPath,
    artifact_id: Annotated[uuid.UUID, Path(description="Artifact id")],
    service: ExperimentServiceDep,
) -> None:
    """Delete one artifact reference from an experiment."""
    await service.delete_artifact(experiment_id, artifact_id)
