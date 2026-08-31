"""Tests for `TrainingJobService` — lifecycle, pipeline execution, and experiment integration."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.features.ai_extensions import NormalizationStats
from app.models import Candle, Exchange, Market
from app.models.experiment import Experiment
from app.repositories.experiments import ExperimentRepository
from app.repositories.training import TrainingJobRepository
from app.schemas.experiments import ExperimentCreateRequest
from app.schemas.training import TrainingJobCreateRequest
from app.services.experiments import ExperimentService
from app.services.training import TrainingJobService, _sanitize_for_json
from app.training.adapters import load_builtin_model_adapters
from app.training.base import TrainingResult
from app.training.errors import (
    InvalidPredictionInputError,
    InvalidTrainingJobSortError,
    PredictionNotAvailableError,
    TrainingJobNotCancellableError,
    TrainingJobNotFoundError,
)
from app.training.normalization import apply_normalization
from app.training.pipeline import TrainingPipeline
from app.training.registry import default_registry
from tests.conftest import SessionFactory
from tests.ml_datasets.test_service import build_service as build_ml_dataset_service


def build_service(session_factory: SessionFactory) -> TrainingJobService:
    load_builtin_model_adapters()
    session = session_factory()
    return TrainingJobService(
        repository=TrainingJobRepository(session),
        experiment_service=ExperimentService(repository=ExperimentRepository(session)),
        pipeline=TrainingPipeline(default_registry),
        ml_dataset_service=build_ml_dataset_service(session_factory),
    )


async def seed_experiment(session_factory: SessionFactory, **overrides: object) -> str:
    service = ExperimentService(repository=ExperimentRepository(session_factory()))
    payload = {"name": "training target experiment"}
    payload.update(overrides)
    experiment = await service.create(ExperimentCreateRequest(**payload))
    return experiment.id


async def seed_real_candles(
    session_factory: SessionFactory, *, symbol: str = "REALUSD", count: int = 80
) -> None:
    """A wobbling (not monotonic) hourly price series long enough to leave a non-empty
    train/validation/test split after horizon trimming, with both 'up' and 'down'
    next_direction labels present so a classifier has more than one class to learn."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=symbol,
            base_asset=symbol[:3],
            quote_asset=symbol[3:],
            market_type="perpetual",
        )
        session.add(market)
        await session.commit()

        price = 100.0
        for i in range(count):
            # A deterministic wobble: up two, down one, repeating — guarantees both
            # 'up' and 'down' next_direction labels occur across the series.
            price += 3.0 if i % 3 != 0 else -4.0
            open_time = base + timedelta(hours=i)
            session.add(
                Candle(
                    market_id=market.id,
                    timeframe="1h",
                    open_time=open_time,
                    close_time=open_time + timedelta(hours=1),
                    open=Decimal(str(price)),
                    high=Decimal(str(price + 2)),
                    low=Decimal(str(price - 2)),
                    close=Decimal(str(price)),
                    volume=Decimal("100"),
                    quote_volume=None,
                    trade_count=None,
                    source="delta",
                )
            )
        await session.commit()


async def seed_experiment_with_real_config(
    session_factory: SessionFactory, *, target: str = "next_direction"
) -> str:
    """An experiment whose feature_set/target_config are real, resolvable requests —
    what a `requires_real_data` adapter needs `load_dataset` to build a dataset from."""
    async with session_factory() as session:
        experiment = Experiment(
            name="real data experiment",
            dataset_version="ds-real",
            feature_set=[{"feature": "ohlcv", "params": {}}],
            target_config=[{"target": target, "params": {"horizon": "1"}}],
            split_config={"train": 0.7, "validation": 0.15, "test": 0.15},
        )
        session.add(experiment)
        await session.commit()
        return str(experiment.id)


@pytest.mark.asyncio
class TestCreate:
    async def test_creates_a_pending_job(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-abc")
        service = build_service(session_factory)

        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        assert job.status == "pending"
        assert job.model_type == "placeholder"
        assert job.dataset_version == "ds-abc"
        assert job.logs == []

    async def test_dataset_version_override_takes_precedence(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-abc")
        service = build_service(session_factory)

        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id, model_type="placeholder", dataset_version="ds-override"
            )
        )

        assert job.dataset_version == "ds-override"

    async def test_normalize_features_defaults_to_true(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-abc")
        service = build_service(session_factory)

        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        assert job.normalize_features is True

    async def test_normalize_features_can_be_disabled(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-abc")
        service = build_service(session_factory)

        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id, model_type="placeholder", normalize_features=False
            )
        )

        assert job.normalize_features is False

    async def test_raises_experiment_not_found_for_an_unknown_experiment(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        from app.services.experiments import ExperimentNotFoundError

        with pytest.raises(ExperimentNotFoundError):
            await service.create(
                TrainingJobCreateRequest(experiment_id=uuid.uuid4(), model_type="placeholder")
            )


@pytest.mark.asyncio
class TestGetAndSearch:
    async def test_get_returns_an_existing_job(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)
        service = build_service(session_factory)
        created = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        fetched = await service.get(uuid.UUID(created.id))

        assert fetched.id == created.id
        assert fetched.model_type == "placeholder"

    async def test_get_raises_not_found_for_an_unknown_id(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(TrainingJobNotFoundError):
            await service.get(uuid.uuid4())

    async def test_search_filters_by_experiment(self, session_factory: SessionFactory) -> None:
        exp_a = await seed_experiment(session_factory, name="a")
        exp_b = await seed_experiment(session_factory, name="b")
        service = build_service(session_factory)
        await service.create(
            TrainingJobCreateRequest(experiment_id=exp_a, model_type="placeholder")
        )
        await service.create(
            TrainingJobCreateRequest(experiment_id=exp_b, model_type="placeholder")
        )

        result = await service.search(
            experiment_id=uuid.UUID(exp_a),
            status_filter=None,
            model_type=None,
            sort="created_at",
            direction="asc",
            limit=10,
            offset=0,
        )

        assert result.total == 1
        assert result.jobs[0].experiment_id == exp_a

    async def test_search_rejects_an_invalid_sort_column(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        with pytest.raises(InvalidTrainingJobSortError):
            await service.search(
                experiment_id=None,
                status_filter=None,
                model_type=None,
                sort="not_a_column",
                direction="asc",
                limit=10,
                offset=0,
            )


@pytest.mark.asyncio
class TestDelete:
    async def test_deletes_a_pending_job(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        await service.delete(uuid.UUID(job.id))

        with pytest.raises(TrainingJobNotFoundError):
            await service.get(uuid.UUID(job.id))

    async def test_refuses_to_delete_a_running_job(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-1")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        repo = TrainingJobRepository(session_factory())
        running_job = await repo.get_by_id(uuid.UUID(job.id))
        assert running_job is not None
        await repo.update(running_job, {"status": "running"})

        with pytest.raises(TrainingJobNotCancellableError):
            await service.delete(uuid.UUID(job.id))


@pytest.mark.asyncio
class TestCancel:
    async def test_cancels_a_pending_job(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory)
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        cancelled = await service.cancel(uuid.UUID(job.id))

        assert cancelled.status == "cancelled"
        assert cancelled.completed_at is not None


@pytest.mark.asyncio
class TestRun:
    async def test_completes_and_updates_the_linked_experiment(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-run")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="placeholder",
                hyperparameters={"epochs": 3},
            )
        )

        completed = await service.run(uuid.UUID(job.id))

        assert completed.status == "completed"
        assert completed.current_stage == "update_experiment"
        assert completed.started_at is not None
        assert completed.completed_at is not None
        assert completed.result_summary is not None
        assert "placeholder_loss" in completed.result_summary["metrics"]
        assert any(log.stage == "execute_training" for log in completed.logs)

        experiment = await ExperimentService(
            repository=ExperimentRepository(session_factory())
        ).get(uuid.UUID(experiment_id))
        assert experiment.status == "completed"
        assert any(m.name == "placeholder_loss" for m in experiment.metrics)
        assert any(a.artifact_type == "model_checkpoint" for a in experiment.artifacts)

    async def test_fails_when_experiment_has_no_dataset_version(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)  # no dataset_version
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        failed = await service.run(uuid.UUID(job.id))

        assert failed.status == "failed"
        assert failed.error_message is not None
        assert "dataset_version" in failed.error_message
        assert failed.error_detail is not None
        assert failed.error_detail["reason"] == failed.error_message
        assert failed.error_detail["suggested_fix"]

        experiment = await ExperimentService(
            repository=ExperimentRepository(session_factory())
        ).get(uuid.UUID(experiment_id))
        assert experiment.status == "failed"

    async def test_fails_for_an_unknown_model_adapter(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-1")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="does-not-exist")
        )

        failed = await service.run(uuid.UUID(job.id))

        assert failed.status == "failed"

    async def test_run_failure_is_resilient_to_the_experiment_already_being_gone(
        self, session_factory: SessionFactory
    ) -> None:
        """A best-effort `_mark_experiment_failed` must not blow up `run()` itself."""
        experiment_id = await seed_experiment(session_factory)  # no dataset_version -> fails
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        exp_repo = ExperimentRepository(session_factory())
        experiment = await exp_repo.get_by_id(uuid.UUID(experiment_id))
        assert experiment is not None
        await exp_repo.delete(experiment)

        failed = await service.run(uuid.UUID(job.id))

        assert failed.status == "failed"

    async def test_cannot_run_a_job_twice(self, session_factory: SessionFactory) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-1")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        await service.run(uuid.UUID(job.id))

        from app.training.errors import InvalidTrainingJobTransitionError

        with pytest.raises(InvalidTrainingJobTransitionError):
            await service.run(uuid.UUID(job.id))


class TestSanitizeForJson:
    """`_sanitize_for_json` — the guard against `training_jobs.result_summary`
    (a Postgres `JSON` column) ever receiving a non-finite float. A one-vs-rest
    ROC-AUC/average-precision for a class that never appears as a negative (or
    positive) example in a split is a real, well-documented scikit-learn `NaN`,
    not a bug in this platform's own math — and `NaN`/`Infinity`/`-Infinity` have
    no JSON literal (RFC 8259), so persisting one outright fails the `UPDATE`."""

    def test_replaces_nan_and_infinity_with_none(self) -> None:
        assert _sanitize_for_json(float("nan")) is None
        assert _sanitize_for_json(float("inf")) is None
        assert _sanitize_for_json(float("-inf")) is None

    def test_leaves_finite_values_untouched(self) -> None:
        assert _sanitize_for_json(1.5) == 1.5
        assert _sanitize_for_json("nan") == "nan"  # a string, not a float
        assert _sanitize_for_json(None) is None
        assert _sanitize_for_json(True) is True

    def test_recurses_into_nested_dicts_and_lists(self) -> None:
        value = {
            "auc": {"up": float("nan"), "down": 0.9},
            "curves": [{"fpr": [0.0, float("nan"), 1.0]}],
            "macro_auc": float("nan"),
        }
        assert _sanitize_for_json(value) == {
            "auc": {"up": None, "down": 0.9},
            "curves": [{"fpr": [0.0, None, 1.0]}],
            "macro_auc": None,
        }


class TestSaveResultsSanitizesNonFiniteFloats:
    async def test_a_nan_metric_is_persisted_as_null_instead_of_failing_the_update(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-nan")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )
        save_results = service._make_save_results_hook(uuid.UUID(job.id))

        # Exactly the shape that broke `POST /training-jobs/{id}/run` with a real
        # Postgres backend (`invalid input syntax for type json ... Token "NaN" is
        # invalid`) before this fix — a degenerate one-vs-rest AUC for a class with
        # no negative examples in the split.
        await save_results(
            TrainingResult(
                metrics={"accuracy": 1.0, "roc_auc": float("nan")},
                artifact_uri="file:///tmp/model.joblib",
                summary={"roc_pr_curves": {"auc": {"up": float("nan"), "down": 0.9}}},
            )
        )

        updated = await service.get(uuid.UUID(job.id))
        assert updated.result_summary is not None
        assert updated.result_summary["metrics"]["roc_auc"] is None
        assert updated.result_summary["metrics"]["accuracy"] == 1.0
        assert updated.result_summary["roc_pr_curves"]["auc"]["up"] is None
        assert updated.result_summary["roc_pr_curves"]["auc"]["down"] == 0.9


class TestListModelAdapters:
    def test_lists_the_placeholder_adapter(self, session_factory: SessionFactory) -> None:
        service = build_service(session_factory)
        catalog = service.list_model_adapters()
        names = [a.name for a in catalog.adapters]
        assert "placeholder" in names

    def test_lists_the_real_baseline_adapters_with_their_model_kind(
        self, session_factory: SessionFactory
    ) -> None:
        service = build_service(session_factory)
        catalog = service.list_model_adapters()
        by_name = {a.name: a for a in catalog.adapters}
        assert by_name["logistic_regression"].model_kind == "classification"
        assert by_name["logistic_regression"].requires_real_data is True
        assert by_name["linear_regression"].model_kind == "regression"
        assert by_name["linear_regression"].requires_real_data is True


@pytest.mark.asyncio
class TestRealDataTraining:
    """End-to-end `run()` against real candles, exercising the baseline model framework."""

    async def test_logistic_regression_trains_on_real_data_and_updates_the_experiment(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="LOGUSD")
        experiment_id = await seed_experiment_with_real_config(
            session_factory, target="next_direction"
        )
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="logistic_regression",
                symbol="LOGUSD",
                timeframe="1h",
            )
        )

        completed = await service.run(uuid.UUID(job.id))

        assert completed.status == "completed"
        assert completed.result_summary is not None
        metrics = completed.result_summary["metrics"]
        assert "accuracy" in metrics
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1" in metrics
        assert "confusion_matrix" in completed.result_summary
        assert completed.result_summary["artifact_uri"].startswith("file://")

        summary = completed.result_summary
        assert "train_metrics" in summary
        assert "test_metrics" in summary
        assert "overfitting" in summary
        assert "confusion_matrix_details" in summary
        assert "roc_pr_curves" in summary
        assert "feature_importance" in summary
        assert "prediction_samples" in summary
        assert summary["model_metadata"]["feature_count"] == len(summary["feature_columns"])
        assert summary["model_metadata"]["sample_count"] > 0
        artifact_types = set(summary["artifacts"])
        assert artifact_types == {
            "metrics_json",
            "training_report_json",
            "feature_importance_csv",
            "confusion_matrix_png",
            "roc_curve_png",
            "precision_recall_curve_png",
        }

        experiment = await ExperimentService(
            repository=ExperimentRepository(session_factory())
        ).get(uuid.UUID(experiment_id))
        assert experiment.status == "completed"
        assert any(m.name == "accuracy" for m in experiment.metrics)
        assert any(a.artifact_type == "model_checkpoint" for a in experiment.artifacts)
        assert any(a.artifact_type == "report" for a in experiment.artifacts)
        assert any(a.artifact_type == "plot" for a in experiment.artifacts)

    async def test_linear_regression_trains_on_real_data(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="LINUSD")
        experiment_id = await seed_experiment_with_real_config(session_factory, target="next_close")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="linear_regression",
                symbol="LINUSD",
                timeframe="1h",
            )
        )

        completed = await service.run(uuid.UUID(job.id))

        assert completed.status == "completed"
        metrics = completed.result_summary["metrics"]
        assert "mae" in metrics
        assert "mse" in metrics
        assert "rmse" in metrics
        assert "r2" in metrics
        assert "coefficients" in completed.result_summary

        summary = completed.result_summary
        assert "train_metrics" in summary
        assert "overfitting" in summary
        assert "feature_importance" in summary
        assert "prediction_samples" in summary
        # Regression has no confusion matrix or ROC/PR curves — only report-type
        # artifacts, no plot-type ones.
        assert set(summary["artifacts"]) == {
            "metrics_json",
            "training_report_json",
            "feature_importance_csv",
        }

    async def test_fails_without_a_symbol_and_timeframe(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment_with_real_config(session_factory)
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="logistic_regression")
        )

        failed = await service.run(uuid.UUID(job.id))

        assert failed.status == "failed"
        assert failed.error_message is not None
        assert "symbol" in failed.error_message

    async def test_fails_when_experiment_has_no_feature_or_target_config(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="NOCFGUSD")
        experiment_id = await seed_experiment(session_factory, dataset_version="ds-1")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="logistic_regression",
                symbol="NOCFGUSD",
                timeframe="1h",
            )
        )

        failed = await service.run(uuid.UUID(job.id))

        assert failed.status == "failed"
        assert failed.error_message is not None
        assert "feature_set/target_config" in failed.error_message

    async def test_fails_with_a_regression_adapter_over_a_categorical_target(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="BADTGTUSD")
        experiment_id = await seed_experiment_with_real_config(
            session_factory, target="next_direction"
        )
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="linear_regression",
                symbol="BADTGTUSD",
                timeframe="1h",
            )
        )

        failed = await service.run(uuid.UUID(job.id))

        assert failed.status == "failed"
        assert failed.error_message is not None
        assert "dtype" in failed.error_message


@pytest.mark.asyncio
class TestPredict:
    async def test_predicts_using_a_completed_jobs_model(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="PREDUSD")
        experiment_id = await seed_experiment_with_real_config(
            session_factory, target="next_direction"
        )
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="logistic_regression",
                symbol="PREDUSD",
                timeframe="1h",
            )
        )
        completed = await service.run(uuid.UUID(job.id))
        feature_columns = completed.result_summary["feature_columns"]
        row = [1.0] * len(feature_columns)

        response = await service.predict(uuid.UUID(job.id), [row])

        assert len(response.predictions) == 1
        assert response.feature_columns == feature_columns
        assert response.classes == completed.result_summary["classes"]
        assert response.probabilities is not None
        assert len(response.probabilities[0]) == len(response.classes)
        assert response.confidence_levels[0] in {"high", "medium", "low"}

    async def test_predict_applies_the_same_normalization_transform_it_trained_with(
        self, session_factory: SessionFactory
    ) -> None:
        """The concrete proof: reproducing the identical transform by hand and
        predicting directly through the adapter (bypassing the service
        entirely) must agree exactly with what `service.predict` returns."""
        await seed_real_candles(session_factory, symbol="NORMPREDUSD")
        experiment_id = await seed_experiment_with_real_config(
            session_factory, target="next_direction"
        )
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="logistic_regression",
                symbol="NORMPREDUSD",
                timeframe="1h",
                normalize_features=True,
            )
        )
        completed = await service.run(uuid.UUID(job.id))
        assert completed.result_summary is not None
        assert completed.result_summary["normalization"] is not None
        feature_columns = completed.result_summary["feature_columns"]
        # Deliberately far outside any normalized column's range, so the
        # transform actually moves the numbers rather than happening to be a
        # near-no-op at this particular value.
        raw_row = [1234.5] * len(feature_columns)

        response = await service.predict(uuid.UUID(job.id), [raw_row])

        stats = [NormalizationStats(**entry) for entry in completed.result_summary["normalization"]]
        method = completed.result_summary["normalization_method"]
        normalized_row = apply_normalization([raw_row], stats, method=method)
        assert normalized_row != [raw_row]  # confirms the transform did something
        adapter = default_registry.get("logistic_regression")
        expected_predictions = adapter.predict(
            completed.result_summary["artifact_uri"], normalized_row
        )

        assert response.predictions == expected_predictions

    async def test_predict_does_not_normalize_when_the_job_disabled_it(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="NONORMPREDUSD")
        experiment_id = await seed_experiment_with_real_config(
            session_factory, target="next_direction"
        )
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="logistic_regression",
                symbol="NONORMPREDUSD",
                timeframe="1h",
                normalize_features=False,
            )
        )
        completed = await service.run(uuid.UUID(job.id))
        assert completed.result_summary is not None
        assert completed.result_summary["normalization"] is None
        feature_columns = completed.result_summary["feature_columns"]
        raw_row = [1.0] * len(feature_columns)

        response = await service.predict(uuid.UUID(job.id), [raw_row])

        adapter = default_registry.get("logistic_regression")
        expected_predictions = adapter.predict(completed.result_summary["artifact_uri"], [raw_row])
        assert response.predictions == expected_predictions

    async def test_a_regression_adapter_returns_no_probabilities_or_confidence(
        self, session_factory: SessionFactory
    ) -> None:
        """`LinearRegressionAdapter` never overrides `predict_proba` — the base
        class's default `None` should flow all the way through to the response,
        not be silently coerced into a fabricated value."""
        await seed_real_candles(session_factory, symbol="PREDREGUSD")
        experiment_id = await seed_experiment_with_real_config(session_factory, target="next_close")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="linear_regression",
                symbol="PREDREGUSD",
                timeframe="1h",
            )
        )
        completed = await service.run(uuid.UUID(job.id))
        feature_columns = completed.result_summary["feature_columns"]
        row = [1.0] * len(feature_columns)

        response = await service.predict(uuid.UUID(job.id), [row])

        assert len(response.predictions) == 1
        assert response.probabilities is None
        assert response.confidence_levels is None
        assert response.classes is None

    async def test_raises_when_the_job_has_not_completed(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        with pytest.raises(PredictionNotAvailableError):
            await service.predict(uuid.UUID(job.id), [[1.0]])

    async def test_raises_for_a_row_length_mismatch(self, session_factory: SessionFactory) -> None:
        await seed_real_candles(session_factory, symbol="MISMATCHUSD")
        experiment_id = await seed_experiment_with_real_config(
            session_factory, target="next_direction"
        )
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="logistic_regression",
                symbol="MISMATCHUSD",
                timeframe="1h",
            )
        )
        await service.run(uuid.UUID(job.id))

        with pytest.raises(InvalidPredictionInputError):
            await service.predict(uuid.UUID(job.id), [[1.0, 2.0, 3.0, 999.0]])

    async def test_raises_prediction_execution_error_when_the_adapter_predict_raises(
        self, session_factory: SessionFactory
    ) -> None:
        from app.training.errors import PredictionExecutionError

        await seed_real_candles(session_factory, symbol="BROKENARTIFACTUSD")
        experiment_id = await seed_experiment_with_real_config(
            session_factory, target="next_direction"
        )
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="logistic_regression",
                symbol="BROKENARTIFACTUSD",
                timeframe="1h",
            )
        )
        completed = await service.run(uuid.UUID(job.id))

        # Corrupt the recorded artifact_uri so the adapter's own `joblib.load` fails —
        # the one path that exercises `predict()`'s own exception-wrapping branch.
        repo = TrainingJobRepository(session_factory())
        stored = await repo.get_by_id(uuid.UUID(job.id))
        assert stored is not None
        broken_summary = dict(stored.result_summary or {})
        broken_summary["artifact_uri"] = "file:///no/such/path.joblib"
        await repo.update(stored, {"result_summary": broken_summary})

        with pytest.raises(PredictionExecutionError):
            await service.predict(
                uuid.UUID(job.id), [[1.0] * len(completed.result_summary["feature_columns"])]
            )


@pytest.mark.asyncio
class TestArtifacts:
    """`list_artifacts`/`get_artifact_file` — the Artifact Management download surface."""

    async def test_lists_every_artifact_for_a_completed_classification_job(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="ARTIFACTLISTUSD")
        experiment_id = await seed_experiment_with_real_config(
            session_factory, target="next_direction"
        )
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="logistic_regression",
                symbol="ARTIFACTLISTUSD",
                timeframe="1h",
            )
        )
        await service.run(uuid.UUID(job.id))

        listing = await service.list_artifacts(uuid.UUID(job.id))

        types = {entry.artifact_type for entry in listing.artifacts}
        assert types == {
            "model_joblib",
            "metrics_json",
            "training_report_json",
            "feature_importance_csv",
            "confusion_matrix_png",
            "roc_curve_png",
            "precision_recall_curve_png",
        }
        model_entry = next(e for e in listing.artifacts if e.artifact_type == "model_joblib")
        assert model_entry.download_url == f"/api/v1/training-jobs/{job.id}/artifacts/model_joblib"
        csv_entry = next(
            e for e in listing.artifacts if e.artifact_type == "feature_importance_csv"
        )
        assert csv_entry.content_type == "text/csv"
        png_entry = next(e for e in listing.artifacts if e.artifact_type == "confusion_matrix_png")
        assert png_entry.content_type == "image/png"

    async def test_lists_no_artifacts_for_a_job_that_has_not_run(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        listing = await service.list_artifacts(uuid.UUID(job.id))

        assert listing.artifacts == []

    async def test_get_artifact_file_resolves_a_real_file_on_disk(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="ARTIFACTGETUSD")
        experiment_id = await seed_experiment_with_real_config(session_factory, target="next_close")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="linear_regression",
                symbol="ARTIFACTGETUSD",
                timeframe="1h",
            )
        )
        await service.run(uuid.UUID(job.id))

        path, content_type = await service.get_artifact_file(uuid.UUID(job.id), "metrics_json")

        assert path.exists()
        assert content_type == "application/json"

    async def test_raises_not_found_for_an_unknown_artifact_type(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="ARTIFACT404USD")
        experiment_id = await seed_experiment_with_real_config(session_factory, target="next_close")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="linear_regression",
                symbol="ARTIFACT404USD",
                timeframe="1h",
            )
        )
        await service.run(uuid.UUID(job.id))

        from app.training.errors import TrainingArtifactNotFoundError

        with pytest.raises(TrainingArtifactNotFoundError):
            await service.get_artifact_file(uuid.UUID(job.id), "roc_curve_png")

    async def test_raises_not_found_when_the_recorded_file_is_missing_from_disk(
        self, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="ARTIFACTGONEUSD")
        experiment_id = await seed_experiment_with_real_config(session_factory, target="next_close")
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(
                experiment_id=experiment_id,
                model_type="linear_regression",
                symbol="ARTIFACTGONEUSD",
                timeframe="1h",
            )
        )
        await service.run(uuid.UUID(job.id))

        repo = TrainingJobRepository(session_factory())
        stored = await repo.get_by_id(uuid.UUID(job.id))
        assert stored is not None
        broken_summary = dict(stored.result_summary or {})
        broken_summary["artifacts"] = dict(broken_summary["artifacts"])
        broken_summary["artifacts"]["metrics_json"] = "file:///no/such/metrics.json"
        await repo.update(stored, {"result_summary": broken_summary})

        from app.training.errors import TrainingArtifactNotFoundError

        with pytest.raises(TrainingArtifactNotFoundError):
            await service.get_artifact_file(uuid.UUID(job.id), "metrics_json")

    async def test_raises_not_found_when_the_job_has_no_result_summary_yet(
        self, session_factory: SessionFactory
    ) -> None:
        experiment_id = await seed_experiment(session_factory)
        service = build_service(session_factory)
        job = await service.create(
            TrainingJobCreateRequest(experiment_id=experiment_id, model_type="placeholder")
        )

        from app.training.errors import TrainingArtifactNotFoundError

        with pytest.raises(TrainingArtifactNotFoundError):
            await service.get_artifact_file(uuid.UUID(job.id), "model_joblib")
