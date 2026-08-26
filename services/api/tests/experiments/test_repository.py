"""Tests for the experiment repository — CRUD, search, filter, and sort."""

import uuid

import pytest

from app.models.experiment import Experiment, ExperimentArtifact, ExperimentMetric
from app.repositories.experiments import ExperimentFilters, ExperimentRepository
from tests.conftest import SessionFactory


async def seed_experiment(
    session_factory: SessionFactory,
    *,
    name: str,
    status: str = "draft",
    model_type: str | None = None,
    dataset_version: str | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
) -> uuid.UUID:
    async with session_factory() as session:
        repo = ExperimentRepository(session)
        experiment = Experiment(
            name=name,
            status=status,
            model_type=model_type,
            dataset_version=dataset_version,
            notes=notes,
        )
        created = await repo.create(experiment)
        if tags:
            created = await repo.replace_tags(created, tags)
        return created.id


@pytest.mark.asyncio
class TestCreateAndGet:
    async def test_creates_and_retrieves_an_experiment(
        self, session_factory: SessionFactory
    ) -> None:
        async with session_factory() as session:
            repo = ExperimentRepository(session)
            created = await repo.create(Experiment(name="baseline sma", status="draft"))

        async with session_factory() as session:
            found = await ExperimentRepository(session).get_by_id(created.id)

        assert found is not None
        assert found.name == "baseline sma"
        assert found.status == "draft"
        assert found.tags == []
        assert found.metrics == []
        assert found.artifacts == []

    async def test_returns_none_for_an_unknown_id(self, session_factory: SessionFactory) -> None:
        async with session_factory() as session:
            found = await ExperimentRepository(session).get_by_id(uuid.uuid4())
        assert found is None

    async def test_persists_json_config_columns(self, session_factory: SessionFactory) -> None:
        async with session_factory() as session:
            repo = ExperimentRepository(session)
            created = await repo.create(
                Experiment(
                    name="with config",
                    feature_set=[{"feature": "sma", "params": {"period": "20"}}],
                    target_config=[{"target": "next_close", "params": {"horizon": "1"}}],
                    split_config={"train": 0.7, "validation": 0.15, "test": 0.15},
                )
            )

        async with session_factory() as session:
            found = await ExperimentRepository(session).get_by_id(created.id)

        assert found is not None
        assert found.feature_set == [{"feature": "sma", "params": {"period": "20"}}]
        assert found.target_config == [{"target": "next_close", "params": {"horizon": "1"}}]
        assert found.split_config == {"train": 0.7, "validation": 0.15, "test": 0.15}


@pytest.mark.asyncio
class TestTags:
    async def test_replace_tags_adds_and_removes(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory, name="tagged", tags=["a", "b"])

        async with session_factory() as session:
            repo = ExperimentRepository(session)
            experiment = await repo.get_by_id(experiment_id)
            assert experiment is not None
            updated = await repo.replace_tags(experiment, ["b", "c"])

        assert sorted(t.tag for t in updated.tags) == ["b", "c"]

    async def test_replace_tags_deduplicates(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory, name="deduped")

        async with session_factory() as session:
            repo = ExperimentRepository(session)
            experiment = await repo.get_by_id(experiment_id)
            assert experiment is not None
            updated = await repo.replace_tags(experiment, ["x", "x", "y"])

        assert sorted(t.tag for t in updated.tags) == ["x", "y"]


@pytest.mark.asyncio
class TestUpdateAndDelete:
    async def test_update_applies_only_given_fields(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory, name="original", status="draft")

        async with session_factory() as session:
            repo = ExperimentRepository(session)
            experiment = await repo.get_by_id(experiment_id)
            assert experiment is not None
            updated = await repo.update(experiment, {"status": "running"})

        assert updated.status == "running"
        assert updated.name == "original"

    async def test_update_can_clear_a_nullable_field(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(
            session_factory, name="has model", model_type="xgboost"
        )

        async with session_factory() as session:
            repo = ExperimentRepository(session)
            experiment = await repo.get_by_id(experiment_id)
            assert experiment is not None
            updated = await repo.update(experiment, {"model_type": None})

        assert updated.model_type is None

    async def test_delete_removes_the_experiment_and_its_children(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, name="to delete")

        async with session_factory() as session:
            repo = ExperimentRepository(session)
            metric = await repo.add_metric(
                ExperimentMetric(experiment_id=experiment_id, name="accuracy", value=0.9)
            )
            artifact = await repo.add_artifact(
                ExperimentArtifact(
                    experiment_id=experiment_id, artifact_type="report", uri="report.pdf"
                )
            )

        async with session_factory() as session:
            repo = ExperimentRepository(session)
            experiment = await repo.get_by_id(experiment_id)
            assert experiment is not None
            await repo.delete(experiment)

        async with session_factory() as session:
            repo = ExperimentRepository(session)
            assert await repo.get_by_id(experiment_id) is None
            assert await repo.get_metric(experiment_id, metric.id) is None
            assert await repo.get_artifact(experiment_id, artifact.id) is None


@pytest.mark.asyncio
class TestMetricsAndArtifacts:
    async def test_add_and_delete_a_metric(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory, name="metric test")

        async with session_factory() as session:
            repo = ExperimentRepository(session)
            metric = await repo.add_metric(
                ExperimentMetric(
                    experiment_id=experiment_id, name="sharpe_ratio", value=1.5, unit="ratio"
                )
            )
            assert metric.name == "sharpe_ratio"
            assert metric.value == 1.5

        async with session_factory() as session:
            repo = ExperimentRepository(session)
            found = await repo.get_metric(experiment_id, metric.id)
            assert found is not None
            await repo.delete_metric(found)

        async with session_factory() as session:
            assert await ExperimentRepository(session).get_metric(experiment_id, metric.id) is None

    async def test_add_and_delete_an_artifact(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory, name="artifact test")

        async with session_factory() as session:
            repo = ExperimentRepository(session)
            artifact = await repo.add_artifact(
                ExperimentArtifact(
                    experiment_id=experiment_id,
                    artifact_type="dataset_export",
                    uri="ETHUSD-1h-ml-dataset.csv",
                )
            )
            assert artifact.artifact_type == "dataset_export"

        async with session_factory() as session:
            repo = ExperimentRepository(session)
            found = await repo.get_artifact(experiment_id, artifact.id)
            assert found is not None
            await repo.delete_artifact(found)

        async with session_factory() as session:
            repo = ExperimentRepository(session)
            assert await repo.get_artifact(experiment_id, artifact.id) is None


@pytest.mark.asyncio
class TestSearchFilterSort:
    async def test_search_matches_name_case_insensitively(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_experiment(session_factory, name="Baseline SMA Model")
        await seed_experiment(session_factory, name="LSTM Attempt")

        async with session_factory() as session:
            results, total = await ExperimentRepository(session).search(
                ExperimentFilters(search="sma"),
                sort="created_at",
                direction="asc",
                limit=10,
                offset=0,
            )

        assert total == 1
        assert results[0].name == "Baseline SMA Model"

    async def test_search_matches_notes_too(self, session_factory: SessionFactory) -> None:
        await seed_experiment(session_factory, name="A", notes="promising overfit risk")
        await seed_experiment(session_factory, name="B", notes="nothing notable")

        async with session_factory() as session:
            results, total = await ExperimentRepository(session).search(
                ExperimentFilters(search="overfit"),
                sort="created_at",
                direction="asc",
                limit=10,
                offset=0,
            )

        assert total == 1
        assert results[0].name == "A"

    async def test_filters_by_status(self, session_factory: SessionFactory) -> None:
        await seed_experiment(session_factory, name="running one", status="running")
        await seed_experiment(session_factory, name="draft one", status="draft")

        async with session_factory() as session:
            results, total = await ExperimentRepository(session).search(
                ExperimentFilters(status="running"),
                sort="created_at",
                direction="asc",
                limit=10,
                offset=0,
            )

        assert total == 1
        assert results[0].status == "running"

    async def test_filters_by_model_type(self, session_factory: SessionFactory) -> None:
        await seed_experiment(session_factory, name="xgb", model_type="xgboost")
        await seed_experiment(session_factory, name="lstm", model_type="lstm")

        async with session_factory() as session:
            results, total = await ExperimentRepository(session).search(
                ExperimentFilters(model_type="lstm"),
                sort="created_at",
                direction="asc",
                limit=10,
                offset=0,
            )

        assert total == 1
        assert results[0].model_type == "lstm"

    async def test_filters_by_dataset_version(self, session_factory: SessionFactory) -> None:
        await seed_experiment(session_factory, name="v1", dataset_version="ds-aaa")
        await seed_experiment(session_factory, name="v2", dataset_version="ds-bbb")

        async with session_factory() as session:
            results, total = await ExperimentRepository(session).search(
                ExperimentFilters(dataset_version="ds-bbb"),
                sort="created_at",
                direction="asc",
                limit=10,
                offset=0,
            )

        assert total == 1
        assert results[0].dataset_version == "ds-bbb"

    async def test_filters_by_tag(self, session_factory: SessionFactory) -> None:
        await seed_experiment(session_factory, name="tagged", tags=["overfit-risk"])
        await seed_experiment(session_factory, name="untagged")

        async with session_factory() as session:
            results, total = await ExperimentRepository(session).search(
                ExperimentFilters(tag="overfit-risk"),
                sort="created_at",
                direction="asc",
                limit=10,
                offset=0,
            )

        assert total == 1
        assert results[0].name == "tagged"

    async def test_combines_multiple_filters(self, session_factory: SessionFactory) -> None:
        await seed_experiment(session_factory, name="match", status="running", model_type="lstm")
        await seed_experiment(
            session_factory, name="wrong status", status="draft", model_type="lstm"
        )
        await seed_experiment(
            session_factory, name="wrong model", status="running", model_type="xgboost"
        )

        async with session_factory() as session:
            results, total = await ExperimentRepository(session).search(
                ExperimentFilters(status="running", model_type="lstm"),
                sort="created_at",
                direction="asc",
                limit=10,
                offset=0,
            )

        assert total == 1
        assert results[0].name == "match"

    async def test_sorts_by_name_ascending(self, session_factory: SessionFactory) -> None:
        await seed_experiment(session_factory, name="Charlie")
        await seed_experiment(session_factory, name="Alpha")
        await seed_experiment(session_factory, name="Bravo")

        async with session_factory() as session:
            results, _ = await ExperimentRepository(session).search(
                ExperimentFilters(), sort="name", direction="asc", limit=10, offset=0
            )

        assert [r.name for r in results] == ["Alpha", "Bravo", "Charlie"]

    async def test_sorts_by_name_descending(self, session_factory: SessionFactory) -> None:
        await seed_experiment(session_factory, name="Charlie")
        await seed_experiment(session_factory, name="Alpha")
        await seed_experiment(session_factory, name="Bravo")

        async with session_factory() as session:
            results, _ = await ExperimentRepository(session).search(
                ExperimentFilters(), sort="name", direction="desc", limit=10, offset=0
            )

        assert [r.name for r in results] == ["Charlie", "Bravo", "Alpha"]

    async def test_paginates_with_limit_and_offset(self, session_factory: SessionFactory) -> None:
        for name in ["one", "two", "three", "four"]:
            await seed_experiment(session_factory, name=name)

        async with session_factory() as session:
            page, total = await ExperimentRepository(session).search(
                ExperimentFilters(), sort="name", direction="asc", limit=2, offset=1
            )

        assert total == 4
        assert len(page) == 2

    async def test_total_reflects_the_full_match_count_not_the_page_size(
        self, session_factory: SessionFactory
    ) -> None:
        for name in ["one", "two", "three"]:
            await seed_experiment(session_factory, name=name)

        async with session_factory() as session:
            page, total = await ExperimentRepository(session).search(
                ExperimentFilters(), sort="name", direction="asc", limit=1, offset=0
            )

        assert total == 3
        assert len(page) == 1
