"""Tests for `MetricRegistry` and the builtin metrics' registration."""

import pytest

from app.evaluation.base import Metric, MetricMetadata
from app.evaluation.errors import DuplicateMetricError, MetricNotFoundError
from app.evaluation.metrics import load_builtin_metrics
from app.evaluation.registry import MetricRegistry, default_registry


class _FakeMetric(Metric):
    metadata = MetricMetadata(
        name="fake",
        label="Fake",
        description="test double",
        category="classification",
        higher_is_better=True,
    )

    def compute(self, y_true, y_pred, y_proba=None):  # noqa: ANN001, ANN201 - test double
        return 1.0


class TestRegister:
    def test_registers_and_resolves_by_name(self) -> None:
        registry = MetricRegistry()
        registry.register(_FakeMetric)
        assert registry.has("fake") is True
        assert isinstance(registry.get("fake"), _FakeMetric)

    def test_rejects_a_class_with_no_metadata(self) -> None:
        registry = MetricRegistry()

        class NoMetadata(Metric):
            def compute(self, y_true, y_pred, y_proba=None):  # noqa: ANN001, ANN201
                return 0.0

        with pytest.raises(TypeError):
            registry.register(NoMetadata)

    def test_rejects_a_duplicate_name(self) -> None:
        registry = MetricRegistry()
        registry.register(_FakeMetric)
        with pytest.raises(DuplicateMetricError):
            registry.register(_FakeMetric)


class TestGet:
    def test_raises_metric_not_found_for_an_unknown_name(self) -> None:
        registry = MetricRegistry()
        with pytest.raises(MetricNotFoundError):
            registry.get("nope")


class TestForCategory:
    def test_filters_by_category(self) -> None:
        registry = MetricRegistry()
        registry.register(_FakeMetric)
        assert [m.metadata.name for m in registry.for_category("classification")] == ["fake"]
        assert registry.for_category("regression") == []


class TestBuiltinMetrics:
    def test_registers_every_documented_metric(self) -> None:
        load_builtin_metrics()
        names = default_registry.names()
        assert {"accuracy", "precision", "recall", "f1", "roc_auc"} <= set(names)
        assert {"mae", "mse", "rmse", "r2"} <= set(names)

    def test_describe_all_is_sorted_by_name(self) -> None:
        load_builtin_metrics()
        names = [metadata.name for metadata in default_registry.describe_all()]
        assert names == sorted(names)

    def test_len_and_iter(self) -> None:
        load_builtin_metrics()
        assert len(default_registry) == len(list(default_registry))
