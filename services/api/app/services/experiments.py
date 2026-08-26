"""Experiment Management service — CRUD, search/filter/sort, metrics, and artifacts.

Composes `ExperimentRepository` the same way `MarketDataService` composes
`CandleRepository`/`MarketRepository`: routers never touch SQL directly,
they call this service, which is the one place domain errors are raised.
"""

import uuid
from typing import Any

from fastapi import status

from app.core.exceptions import AppError
from app.models.experiment import Experiment, ExperimentArtifact, ExperimentMetric
from app.repositories.experiments import (
    SORT_COLUMNS,
    ExperimentFilters,
    ExperimentRepository,
)
from app.schemas.experiments import (
    ArtifactCreateRequest,
    ArtifactDTO,
    ExperimentCreateRequest,
    ExperimentListResponse,
    ExperimentResponse,
    ExperimentSummaryDTO,
    ExperimentUpdateRequest,
    MetricCreateRequest,
    MetricDTO,
)


class ExperimentNotFoundError(AppError):
    """Raised when the requested experiment id does not exist."""

    def __init__(self, experiment_id: uuid.UUID) -> None:
        super().__init__(
            f"Experiment {experiment_id} not found",
            code="experiment_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class MetricNotFoundError(AppError):
    """Raised when the requested metric id does not exist on the experiment."""

    def __init__(self, metric_id: uuid.UUID) -> None:
        super().__init__(
            f"Metric {metric_id} not found",
            code="metric_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ArtifactNotFoundError(AppError):
    """Raised when the requested artifact id does not exist on the experiment."""

    def __init__(self, artifact_id: uuid.UUID) -> None:
        super().__init__(
            f"Artifact {artifact_id} not found",
            code="artifact_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidExperimentSortError(AppError):
    """Raised when the sort column or direction is unsupported."""

    def __init__(self, sort: str, direction: str) -> None:
        columns = ", ".join(sorted(SORT_COLUMNS))
        super().__init__(
            f"Unsupported sort {sort!r} (direction {direction!r}); "
            f"supported columns: {columns}, directions: asc, desc",
            code="invalid_sort",
        )


class ExperimentService:
    """The one entry point routers use for every experiment operation."""

    def __init__(self, repository: ExperimentRepository) -> None:
        self.repository = repository

    async def create(self, payload: ExperimentCreateRequest) -> ExperimentResponse:
        experiment = Experiment(
            name=payload.name,
            dataset_version=payload.dataset_version,
            feature_set=[item.model_dump() for item in payload.feature_set]
            if payload.feature_set is not None
            else None,
            target_config=[item.model_dump() for item in payload.target_config]
            if payload.target_config is not None
            else None,
            split_config=payload.split_config.model_dump() if payload.split_config else None,
            model_type=payload.model_type,
            status=payload.status,
            notes=payload.notes,
        )
        created = await self.repository.create(experiment)
        if payload.tags:
            created = await self.repository.replace_tags(created, payload.tags)
        return ExperimentResponse.from_model(created)

    async def get(self, experiment_id: uuid.UUID) -> ExperimentResponse:
        experiment = await self.repository.get_by_id(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        return ExperimentResponse.from_model(experiment)

    async def search(
        self,
        *,
        search: str | None,
        status_filter: str | None,
        model_type: str | None,
        dataset_version: str | None,
        tag: str | None,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> ExperimentListResponse:
        if sort not in SORT_COLUMNS or direction not in {"asc", "desc"}:
            raise InvalidExperimentSortError(sort, direction)

        filters = ExperimentFilters(
            search=search,
            status=status_filter,
            model_type=model_type,
            dataset_version=dataset_version,
            tag=tag,
        )
        experiments, total = await self.repository.search(
            filters, sort=sort, direction=direction, limit=limit, offset=offset
        )
        return ExperimentListResponse(
            experiments=[ExperimentSummaryDTO.from_model(exp) for exp in experiments],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def update(
        self, experiment_id: uuid.UUID, payload: ExperimentUpdateRequest
    ) -> ExperimentResponse:
        experiment = await self.repository.get_by_id(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)

        updates = payload.model_dump(exclude_unset=True, exclude={"tags"})
        fields: dict[str, Any] = dict(updates)
        if "feature_set" in fields and fields["feature_set"] is not None:
            fields["feature_set"] = [dict(item) for item in fields["feature_set"]]
        if "target_config" in fields and fields["target_config"] is not None:
            fields["target_config"] = [dict(item) for item in fields["target_config"]]
        if "split_config" in fields and fields["split_config"] is not None:
            fields["split_config"] = dict(fields["split_config"])

        if fields:
            experiment = await self.repository.update(experiment, fields)
        if payload.tags is not None:
            experiment = await self.repository.replace_tags(experiment, payload.tags)
        return ExperimentResponse.from_model(experiment)

    async def delete(self, experiment_id: uuid.UUID) -> None:
        experiment = await self.repository.get_by_id(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        await self.repository.delete(experiment)

    async def add_metric(self, experiment_id: uuid.UUID, payload: MetricCreateRequest) -> MetricDTO:
        experiment = await self.repository.get_by_id(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        metric = ExperimentMetric(
            experiment_id=experiment_id,
            name=payload.name,
            value=payload.value,
            unit=payload.unit,
        )
        created = await self.repository.add_metric(metric)
        return MetricDTO.from_model(created)

    async def delete_metric(self, experiment_id: uuid.UUID, metric_id: uuid.UUID) -> None:
        metric = await self.repository.get_metric(experiment_id, metric_id)
        if metric is None:
            raise MetricNotFoundError(metric_id)
        await self.repository.delete_metric(metric)

    async def add_artifact(
        self, experiment_id: uuid.UUID, payload: ArtifactCreateRequest
    ) -> ArtifactDTO:
        experiment = await self.repository.get_by_id(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        artifact = ExperimentArtifact(
            experiment_id=experiment_id,
            artifact_type=payload.artifact_type,
            uri=payload.uri,
            description=payload.description,
        )
        created = await self.repository.add_artifact(artifact)
        return ArtifactDTO.from_model(created)

    async def delete_artifact(self, experiment_id: uuid.UUID, artifact_id: uuid.UUID) -> None:
        artifact = await self.repository.get_artifact(experiment_id, artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(artifact_id)
        await self.repository.delete_artifact(artifact)
