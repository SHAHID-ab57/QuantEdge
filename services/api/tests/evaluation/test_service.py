"""Tests for `EvaluationService` — metric catalogue and benchmark comparison.

`benchmark` is a read-only comparison over `TrainingJob.result_summary`, so
these tests seed `TrainingJob` rows directly (via the repository) rather
than running the full training pipeline — the pipeline's own contribution
to `result_summary["metrics"]` is already covered by
`tests/api/test_training_api.py::TestRealBaselineModels`.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.evaluation.errors import (
    BenchmarkRunNotFoundError,
    EmptyBenchmarkError,
    InvalidBenchmarkRunSortError,
    NoBenchmarkTargetError,
)
from app.evaluation.registry import default_registry as default_metric_registry
from app.models.training import TrainingJob
from app.repositories.evaluation_benchmark_runs import EvaluationBenchmarkRunRepository
from app.repositories.experiments import ExperimentRepository
from app.repositories.training import TrainingJobRepository
from app.schemas.evaluation import BenchmarkRequest
from app.schemas.experiments import ExperimentCreateRequest
from app.services.evaluation import EvaluationService
from app.services.experiments import ExperimentService
from app.training.adapters import load_builtin_model_adapters
from app.training.registry import default_registry as default_model_adapter_registry
from tests.conftest import SessionFactory


def build_service(session_factory: SessionFactory) -> EvaluationService:
    load_builtin_model_adapters()
    session = session_factory()
    return EvaluationService(
        training_repository=TrainingJobRepository(session),
        experiment_service=ExperimentService(repository=ExperimentRepository(session)),
        metric_registry=default_metric_registry,
        model_adapter_registry=default_model_adapter_registry,
        benchmark_run_repository=EvaluationBenchmarkRunRepository(session),
        benchmark_max_candidates=100,
    )


async def seed_experiment(session_factory: SessionFactory, **overrides: object) -> uuid.UUID:
    service = ExperimentService(repository=ExperimentRepository(session_factory()))
    payload = {"name": "benchmark target experiment"}
    payload.update(overrides)
    experiment = await service.create(ExperimentCreateRequest(**payload))
    return uuid.UUID(experiment.id)


async def seed_completed_job(
    session_factory: SessionFactory,
    experiment_id: uuid.UUID,
    *,
    model_type: str = "logistic_regression",
    dataset_version: str | None = "ds-1",
    target_column: str | None = "next_direction",
    symbol: str | None = None,
    timeframe: str | None = None,
    metrics: dict[str, float] | None = None,
    result_summary_extra: dict[str, object] | None = None,
) -> TrainingJob:
    repository = TrainingJobRepository(session_factory())
    result_summary: dict[str, object] = {
        "metrics": metrics if metrics is not None else {"accuracy": 0.9}
    }
    if result_summary_extra:
        result_summary.update(result_summary_extra)
    job = TrainingJob(
        experiment_id=experiment_id,
        model_type=model_type,
        dataset_version=dataset_version,
        target_column=target_column,
        symbol=symbol,
        timeframe=timeframe,
        status="completed",
        hyperparameters={},
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        result_summary=result_summary,
    )
    return await repository.create(job)


class TestListMetrics:
    async def test_returns_every_registered_metric(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        response = service.list_metrics()
        names = {m.name for m in response.metrics}
        assert {"accuracy", "precision", "recall", "f1", "roc_auc"} <= names
        assert {"mae", "mse", "rmse", "r2"} <= names


class TestBenchmark:
    async def test_raises_when_no_target_is_given(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        with pytest.raises(NoBenchmarkTargetError):
            await service.benchmark(BenchmarkRequest())

    async def test_raises_when_nothing_matches(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        with pytest.raises(EmptyBenchmarkError):
            await service.benchmark(BenchmarkRequest(dataset_version="ds-nonexistent"))

    async def test_compares_jobs_sharing_a_dataset_version(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        await seed_completed_job(
            session_factory,
            experiment_id,
            model_type="logistic_regression",
            dataset_version="ds-shared",
            metrics={"accuracy": 0.7, "f1": 0.65},
        )
        await seed_completed_job(
            session_factory,
            experiment_id,
            model_type="logistic_regression",
            dataset_version="ds-shared",
            metrics={"accuracy": 0.9, "f1": 0.85},
        )

        service = build_service(session_factory)
        response = await service.benchmark(BenchmarkRequest(dataset_version="ds-shared"))

        assert len(response.candidates) == 2
        assert all(c.model_kind == "classification" for c in response.candidates)
        assert all(c.experiment_name == "benchmark target experiment" for c in response.candidates)
        best_accuracy = next(e for e in response.best_by_metric if e.metric == "accuracy")
        assert best_accuracy.value == pytest.approx(0.9)

    async def test_narrows_further_by_experiment_ids(self, session_factory: SessionFactory) -> None:
        experiment_a = await seed_experiment(session_factory, name="experiment a")
        experiment_b = await seed_experiment(session_factory, name="experiment b")
        await seed_completed_job(
            session_factory,
            experiment_a,
            dataset_version="ds-shared-2",
            metrics={"accuracy": 0.5},
        )
        await seed_completed_job(
            session_factory,
            experiment_b,
            dataset_version="ds-shared-2",
            metrics={"accuracy": 0.6},
        )

        service = build_service(session_factory)
        response = await service.benchmark(
            BenchmarkRequest(dataset_version="ds-shared-2", experiment_ids=[experiment_a])
        )

        assert len(response.candidates) == 1
        assert response.candidates[0].experiment_id == str(experiment_a)

    async def test_excludes_a_completed_job_with_no_recorded_metrics(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        await seed_completed_job(
            session_factory, experiment_id, dataset_version="ds-empty-metrics", metrics={}
        )

        service = build_service(session_factory)
        with pytest.raises(EmptyBenchmarkError):
            await service.benchmark(BenchmarkRequest(dataset_version="ds-empty-metrics"))

    async def test_an_unregistered_model_type_reports_model_kind_unknown(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        await seed_completed_job(
            session_factory,
            experiment_id,
            model_type="some_future_model",
            dataset_version="ds-future",
            metrics={"accuracy": 0.5},
        )

        service = build_service(session_factory)
        response = await service.benchmark(BenchmarkRequest(dataset_version="ds-future"))

        assert response.candidates[0].model_kind == "unknown"

    async def test_supports_comparing_more_than_two_experiments_at_once(
        self, session_factory: SessionFactory
    ) -> None:
        experiments = [
            await seed_experiment(session_factory, name=f"experiment {i}") for i in range(4)
        ]
        for index, experiment_id in enumerate(experiments):
            await seed_completed_job(
                session_factory,
                experiment_id,
                dataset_version="ds-multi",
                metrics={"accuracy": 0.5 + index * 0.1},
            )

        service = build_service(session_factory)
        response = await service.benchmark(
            BenchmarkRequest(dataset_version="ds-multi", experiment_ids=experiments)
        )

        assert len(response.candidates) == 4
        assert {c.experiment_id for c in response.candidates} == {str(e) for e in experiments}
        best_accuracy = next(e for e in response.best_by_metric if e.metric == "accuracy")
        assert best_accuracy.value == pytest.approx(0.8)

    async def test_candidate_carries_dataset_summary_fields_from_already_computed_data(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        await seed_completed_job(
            session_factory,
            experiment_id,
            dataset_version="ds-summary",
            symbol="ETHUSD",
            timeframe="1h",
            metrics={"accuracy": 0.8},
            result_summary_extra={
                "artifact_uri": "file:///tmp/model.joblib",
                "model_metadata": {"feature_count": 5, "sample_count": 200},
            },
        )

        service = build_service(session_factory)
        response = await service.benchmark(BenchmarkRequest(dataset_version="ds-summary"))

        candidate = response.candidates[0]
        assert candidate.symbol == "ETHUSD"
        assert candidate.timeframe == "1h"
        assert candidate.feature_count == 5
        assert candidate.sample_count == 200
        assert candidate.model_artifact_url is not None
        assert candidate.model_artifact_url.endswith("/artifacts/model_joblib")
        assert candidate.report["model_metadata"]["feature_count"] == 5

    async def test_candidate_omits_artifact_url_when_no_artifact_was_recorded(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        await seed_completed_job(
            session_factory,
            experiment_id,
            dataset_version="ds-no-artifact",
            metrics={"accuracy": 0.8},
        )

        service = build_service(session_factory)
        response = await service.benchmark(BenchmarkRequest(dataset_version="ds-no-artifact"))

        assert response.candidates[0].model_artifact_url is None
        assert response.candidates[0].feature_count is None
        assert response.candidates[0].sample_count is None


class TestBenchmarkHistory:
    async def test_a_successful_benchmark_is_recorded_to_history(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        await seed_completed_job(
            session_factory, experiment_id, dataset_version="ds-history", metrics={"accuracy": 0.8}
        )
        service = build_service(session_factory)

        await service.benchmark(BenchmarkRequest(dataset_version="ds-history"))

        history = await service.list_benchmark_runs(
            dataset_version=None,
            target_column=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        assert history.total == 1
        assert history.runs[0].dataset_version == "ds-history"
        assert history.runs[0].candidate_count == 1

    async def test_reopening_a_run_returns_the_exact_request_and_response(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        await seed_completed_job(
            session_factory, experiment_id, dataset_version="ds-reopen", metrics={"accuracy": 0.8}
        )
        service = build_service(session_factory)
        original = await service.benchmark(BenchmarkRequest(dataset_version="ds-reopen"))

        history = await service.list_benchmark_runs(
            dataset_version="ds-reopen",
            target_column=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        run_id = uuid.UUID(history.runs[0].id)

        detail = await service.get_benchmark_run(run_id)

        assert detail.request.dataset_version == "ds-reopen"
        assert detail.response.candidates[0].metrics == original.candidates[0].metrics

    async def test_get_benchmark_run_raises_for_an_unknown_id(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(BenchmarkRunNotFoundError):
            await service.get_benchmark_run(uuid.uuid4())

    async def test_delete_benchmark_run_removes_it_from_history(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        await seed_completed_job(
            session_factory, experiment_id, dataset_version="ds-delete", metrics={"accuracy": 0.8}
        )
        service = build_service(session_factory)
        await service.benchmark(BenchmarkRequest(dataset_version="ds-delete"))
        history = await service.list_benchmark_runs(
            dataset_version="ds-delete",
            target_column=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        run_id = uuid.UUID(history.runs[0].id)

        await service.delete_benchmark_run(run_id)

        with pytest.raises(BenchmarkRunNotFoundError):
            await service.get_benchmark_run(run_id)

    async def test_delete_benchmark_run_raises_for_an_unknown_id(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(BenchmarkRunNotFoundError):
            await service.delete_benchmark_run(uuid.uuid4())

    async def test_list_benchmark_runs_rejects_an_invalid_sort(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(InvalidBenchmarkRunSortError):
            await service.list_benchmark_runs(
                dataset_version=None,
                target_column=None,
                sort="not_a_real_column",
                direction="desc",
                limit=20,
                offset=0,
            )

    async def test_list_benchmark_runs_filters_by_target_column(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        await seed_completed_job(
            session_factory,
            experiment_id,
            dataset_version="ds-target-a",
            target_column="next_direction",
            metrics={"accuracy": 0.8},
        )
        await seed_completed_job(
            session_factory,
            experiment_id,
            dataset_version="ds-target-b",
            target_column="next_close",
            metrics={"mae": 0.1},
        )
        service = build_service(session_factory)
        await service.benchmark(
            BenchmarkRequest(dataset_version="ds-target-a", target_column="next_direction")
        )
        await service.benchmark(
            BenchmarkRequest(dataset_version="ds-target-b", target_column="next_close")
        )

        history = await service.list_benchmark_runs(
            dataset_version=None,
            target_column="next_close",
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )

        assert history.total == 1
        assert history.runs[0].target_column == "next_close"

    async def test_a_failed_history_persist_does_not_fail_the_benchmark_itself(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`_record_benchmark_run` is best-effort — a researcher must still get
        their comparison back even if Benchmark History fails to persist it."""
        experiment_id = await seed_experiment(session_factory)
        await seed_completed_job(
            session_factory,
            experiment_id,
            dataset_version="ds-history-fails",
            metrics={"accuracy": 0.8},
        )
        service = build_service(session_factory)

        async def broken_create(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(service.benchmark_run_repository, "create", broken_create)

        response = await service.benchmark(BenchmarkRequest(dataset_version="ds-history-fails"))

        assert len(response.candidates) == 1
