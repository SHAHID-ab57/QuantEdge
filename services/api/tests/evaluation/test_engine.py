"""Tests for `EvaluationEngine` — the partial-success evaluation contract."""

from app.evaluation.base import Metric, MetricMetadata
from app.evaluation.engine import EvaluationEngine, default_engine
from app.evaluation.registry import MetricRegistry


class _AlwaysFailsMetric(Metric):
    metadata = MetricMetadata(
        name="always_fails",
        label="Always Fails",
        description="test double that always raises",
        category="classification",
        higher_is_better=True,
    )

    def compute(self, y_true, y_pred, y_proba=None):  # noqa: ANN001, ANN201 - test double
        raise ValueError("boom")


class _RequiresProbaMetric(Metric):
    metadata = MetricMetadata(
        name="needs_proba",
        label="Needs Proba",
        description="test double requiring probabilities",
        category="classification",
        higher_is_better=True,
        requires_probabilities=True,
    )

    def compute(self, y_true, y_pred, y_proba=None):  # noqa: ANN001, ANN201 - test double
        assert y_proba is not None
        return 0.5


class TestEvaluate:
    def test_unknown_model_kind_returns_an_empty_report(self) -> None:
        report = default_engine.evaluate("placeholder", [1, 0], [1, 0])
        assert report.metrics == {}
        assert report.skipped == {}

    def test_real_classification_metrics_populate_the_flat_metrics_dict(self) -> None:
        report = default_engine.evaluate("classification", [1, 0, 1, 1], [1, 0, 0, 1])
        assert "accuracy" in report.metrics
        assert "precision" in report.metrics
        # roc_auc requires probabilities, none given here — skipped, not errored.
        assert "roc_auc" in report.skipped

    def test_real_regression_metrics_populate_the_flat_metrics_dict(self) -> None:
        report = default_engine.evaluate("regression", [1.0, 2.0, 3.0], [1.1, 1.9, 3.2])
        assert {"mae", "mse", "rmse", "r2"} <= report.metrics.keys()

    def test_a_metric_requiring_probabilities_is_skipped_when_none_given(self) -> None:
        registry = MetricRegistry()
        registry.register(_RequiresProbaMetric)
        engine = EvaluationEngine(registry)

        report = engine.evaluate("classification", [1, 0], [1, 0])

        assert report.metrics == {}
        assert "needs_proba" in report.skipped

    def test_a_metric_requiring_probabilities_runs_when_given(self) -> None:
        registry = MetricRegistry()
        registry.register(_RequiresProbaMetric)
        engine = EvaluationEngine(registry)

        report = engine.evaluate("classification", [1, 0], [1, 0], [[0.1, 0.9], [0.8, 0.2]])

        assert report.metrics == {"needs_proba": 0.5}

    def test_a_metric_that_raises_is_recorded_as_skipped_not_propagated(self) -> None:
        registry = MetricRegistry()
        registry.register(_AlwaysFailsMetric)
        engine = EvaluationEngine(registry)

        report = engine.evaluate("classification", [1, 0], [1, 0])

        assert report.metrics == {}
        assert "ValueError" in report.skipped["always_fails"]

    def test_evaluate_never_raises_for_a_bad_metric_alongside_a_good_one(self) -> None:
        registry = MetricRegistry()
        registry.register(_AlwaysFailsMetric)
        registry.register(_RequiresProbaMetric)
        engine = EvaluationEngine(registry)

        report = engine.evaluate("classification", [1, 0], [1, 0], [[0.1, 0.9], [0.8, 0.2]])

        assert report.metrics == {"needs_proba": 0.5}
        assert report.skipped == {"always_fails": "ValueError: boom"}


class TestRegistryProperty:
    def test_exposes_the_registry_it_was_built_with(self) -> None:
        registry = MetricRegistry()
        engine = EvaluationEngine(registry)
        assert engine.registry is registry
