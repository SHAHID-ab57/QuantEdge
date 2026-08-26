"""Tests for `ExperimentService` — the errors and orchestration the repository itself doesn't know about."""

import uuid

import pytest

from app.repositories.experiments import ExperimentRepository
from app.schemas.experiments import (
    ArtifactCreateRequest,
    ExperimentCreateRequest,
    ExperimentUpdateRequest,
    FeatureRequestDTO,
    MetricCreateRequest,
    SplitConfigDTO,
    TargetRequestDTO,
)
from app.services.experiments import (
    ArtifactNotFoundError,
    ExperimentNotFoundError,
    ExperimentService,
    InvalidExperimentSortError,
    MetricNotFoundError,
)
from tests.conftest import SessionFactory


def build_service(session_factory: SessionFactory) -> ExperimentService:
    return ExperimentService(repository=ExperimentRepository(session_factory()))


@pytest.mark.asyncio
class TestCreate:
    async def test_creates_an_experiment_with_full_config(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        response = await service.create(
            ExperimentCreateRequest(
                name="baseline",
                dataset_version="ds-123",
                feature_set=[FeatureRequestDTO(feature="ohlcv")],
                target_config=[TargetRequestDTO(target="next_close", params={"horizon": "1"})],
                split_config=SplitConfigDTO(train=0.7, validation=0.15, test=0.15),
                model_type="xgboost",
                status="draft",
                notes="first attempt",
                tags=["baseline", "sma"],
            )
        )

        assert response.name == "baseline"
        assert response.dataset_version == "ds-123"
        assert response.feature_set == [FeatureRequestDTO(feature="ohlcv")]
        assert response.split_config == SplitConfigDTO(train=0.7, validation=0.15, test=0.15)
        assert response.tags == ["baseline", "sma"]
        assert response.status == "draft"
        assert response.metrics == []
        assert response.artifacts == []

    async def test_defaults_status_to_draft(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        response = await service.create(ExperimentCreateRequest(name="minimal"))
        assert response.status == "draft"
        assert response.tags == []


@pytest.mark.asyncio
class TestGet:
    async def test_returns_the_experiment(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="x"))
        found = await service.get(uuid.UUID(created.id))
        assert found.id == created.id

    async def test_raises_not_found_for_an_unknown_id(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(ExperimentNotFoundError):
            await service.get(uuid.uuid4())


@pytest.mark.asyncio
class TestSearch:
    async def test_returns_a_page_with_pagination_metadata(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        await service.create(ExperimentCreateRequest(name="a"))
        await service.create(ExperimentCreateRequest(name="b"))

        result = await service.search(
            search=None,
            status_filter=None,
            model_type=None,
            dataset_version=None,
            tag=None,
            sort="name",
            direction="asc",
            limit=1,
            offset=0,
        )

        assert result.total == 2
        assert len(result.experiments) == 1
        assert result.limit == 1
        assert result.offset == 0

    async def test_raises_invalid_sort_for_an_unknown_column(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(InvalidExperimentSortError):
            await service.search(
                search=None,
                status_filter=None,
                model_type=None,
                dataset_version=None,
                tag=None,
                sort="score",
                direction="asc",
                limit=10,
                offset=0,
            )

    async def test_raises_invalid_sort_for_an_unknown_direction(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(InvalidExperimentSortError):
            await service.search(
                search=None,
                status_filter=None,
                model_type=None,
                dataset_version=None,
                tag=None,
                sort="name",
                direction="sideways",
                limit=10,
                offset=0,
            )

    async def test_summary_rows_report_metric_and_artifact_counts(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="with children"))
        await service.add_metric(
            uuid.UUID(created.id), MetricCreateRequest(name="accuracy", value=0.9)
        )
        await service.add_artifact(
            uuid.UUID(created.id),
            ArtifactCreateRequest(artifact_type="report", uri="report.pdf"),
        )

        result = await service.search(
            search=None,
            status_filter=None,
            model_type=None,
            dataset_version=None,
            tag=None,
            sort="name",
            direction="asc",
            limit=10,
            offset=0,
        )

        assert result.experiments[0].metric_count == 1
        assert result.experiments[0].artifact_count == 1


@pytest.mark.asyncio
class TestUpdate:
    async def test_applies_a_partial_update(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="before", status="draft"))
        updated = await service.update(
            uuid.UUID(created.id), ExperimentUpdateRequest(status="running")
        )
        assert updated.status == "running"
        assert updated.name == "before"

    async def test_replaces_tags_when_provided(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="tagged", tags=["a"]))
        updated = await service.update(
            uuid.UUID(created.id), ExperimentUpdateRequest(tags=["b", "c"])
        )
        assert updated.tags == ["b", "c"]

    async def test_leaves_tags_untouched_when_omitted(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="tagged", tags=["a"]))
        updated = await service.update(uuid.UUID(created.id), ExperimentUpdateRequest(notes="hi"))
        assert updated.tags == ["a"]
        assert updated.notes == "hi"

    async def test_raises_not_found_for_an_unknown_id(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(ExperimentNotFoundError):
            await service.update(uuid.uuid4(), ExperimentUpdateRequest(notes="x"))

    async def test_updates_feature_set_target_config_and_split_config(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="reconfigured"))
        updated = await service.update(
            uuid.UUID(created.id),
            ExperimentUpdateRequest(
                feature_set=[FeatureRequestDTO(feature="ema", params={"period": "10"})],
                target_config=[TargetRequestDTO(target="next_return")],
                split_config=SplitConfigDTO(train=0.8, validation=0.1, test=0.1),
            ),
        )
        assert updated.feature_set == [FeatureRequestDTO(feature="ema", params={"period": "10"})]
        assert updated.target_config == [TargetRequestDTO(target="next_return")]
        assert updated.split_config == SplitConfigDTO(train=0.8, validation=0.1, test=0.1)


@pytest.mark.asyncio
class TestDelete:
    async def test_deletes_the_experiment(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="to delete"))
        await service.delete(uuid.UUID(created.id))
        with pytest.raises(ExperimentNotFoundError):
            await service.get(uuid.UUID(created.id))

    async def test_raises_not_found_for_an_unknown_id(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(ExperimentNotFoundError):
            await service.delete(uuid.uuid4())


@pytest.mark.asyncio
class TestMetrics:
    async def test_adds_a_metric(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="x"))
        metric = await service.add_metric(
            uuid.UUID(created.id), MetricCreateRequest(name="accuracy", value=0.87, unit="ratio")
        )
        assert metric.name == "accuracy"
        assert metric.value == 0.87

    async def test_raises_not_found_when_the_experiment_does_not_exist(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(ExperimentNotFoundError):
            await service.add_metric(uuid.uuid4(), MetricCreateRequest(name="x", value=1.0))

    async def test_deletes_a_metric(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="x"))
        metric = await service.add_metric(
            uuid.UUID(created.id), MetricCreateRequest(name="accuracy", value=0.9)
        )
        await service.delete_metric(uuid.UUID(created.id), uuid.UUID(metric.id))
        found = await service.get(uuid.UUID(created.id))
        assert found.metrics == []

    async def test_raises_not_found_for_an_unknown_metric(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="x"))
        with pytest.raises(MetricNotFoundError):
            await service.delete_metric(uuid.UUID(created.id), uuid.uuid4())


@pytest.mark.asyncio
class TestArtifacts:
    async def test_adds_an_artifact(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="x"))
        artifact = await service.add_artifact(
            uuid.UUID(created.id),
            ArtifactCreateRequest(artifact_type="dataset_export", uri="data.csv"),
        )
        assert artifact.artifact_type == "dataset_export"
        assert artifact.uri == "data.csv"

    async def test_raises_not_found_when_the_experiment_does_not_exist(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(ExperimentNotFoundError):
            await service.add_artifact(
                uuid.uuid4(), ArtifactCreateRequest(artifact_type="report", uri="x")
            )

    async def test_deletes_an_artifact(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="x"))
        artifact = await service.add_artifact(
            uuid.UUID(created.id),
            ArtifactCreateRequest(artifact_type="report", uri="report.pdf"),
        )
        await service.delete_artifact(uuid.UUID(created.id), uuid.UUID(artifact.id))
        found = await service.get(uuid.UUID(created.id))
        assert found.artifacts == []

    async def test_raises_not_found_for_an_unknown_artifact(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        created = await service.create(ExperimentCreateRequest(name="x"))
        with pytest.raises(ArtifactNotFoundError):
            await service.delete_artifact(uuid.UUID(created.id), uuid.uuid4())
