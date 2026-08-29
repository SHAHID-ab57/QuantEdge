"""Tests for the builtin classification/regression metrics."""

import math

import pytest

from app.evaluation.metrics.classification import (
    AccuracyMetric,
    F1Metric,
    PrecisionMetric,
    RecallMetric,
    RocAucMetric,
)
from app.evaluation.metrics.regression import MaeMetric, MseMetric, R2Metric, RmseMetric


class TestClassificationMetrics:
    y_true = [1, 0, 1, 1, 0]
    y_pred = [1, 0, 0, 1, 0]

    def test_accuracy(self) -> None:
        assert AccuracyMetric().compute(self.y_true, self.y_pred) == pytest.approx(0.8)

    def test_precision(self) -> None:
        value = PrecisionMetric().compute(self.y_true, self.y_pred)
        assert 0.0 <= value <= 1.0

    def test_recall(self) -> None:
        value = RecallMetric().compute(self.y_true, self.y_pred)
        assert 0.0 <= value <= 1.0

    def test_f1(self) -> None:
        value = F1Metric().compute(self.y_true, self.y_pred)
        assert 0.0 <= value <= 1.0

    def test_metadata_declares_higher_is_better(self) -> None:
        for metric in (AccuracyMetric(), PrecisionMetric(), RecallMetric(), F1Metric()):
            assert metric.metadata.higher_is_better is True
            assert metric.metadata.category == "classification"
            assert metric.metadata.requires_probabilities is False


class TestRocAucMetric:
    def test_requires_probabilities_flag(self) -> None:
        assert RocAucMetric().metadata.requires_probabilities is True
        assert RocAucMetric().metadata.higher_is_better is True

    def test_raises_if_called_directly_without_probabilities(self) -> None:
        # `EvaluationEngine` never calls `compute` this way (it skips the metric
        # instead), but `compute` still guards itself for a caller that bypasses
        # the engine.
        with pytest.raises(ValueError, match="requires y_proba"):
            RocAucMetric().compute([0, 1], [0, 1], None)

    def test_binary_case_uses_the_positive_class_column(self) -> None:
        y_true = [0, 0, 1, 1]
        y_proba = [[0.9, 0.1], [0.8, 0.2], [0.3, 0.7], [0.1, 0.9]]
        value = RocAucMetric().compute(y_true, [0, 0, 1, 1], y_proba)
        assert value == pytest.approx(1.0)

    def test_multiclass_case_uses_weighted_ovr(self) -> None:
        y_true = [0, 1, 2, 0, 1, 2]
        y_pred = [0, 1, 2, 0, 1, 2]
        y_proba = [
            [0.8, 0.1, 0.1],
            [0.1, 0.8, 0.1],
            [0.1, 0.1, 0.8],
            [0.7, 0.2, 0.1],
            [0.2, 0.7, 0.1],
            [0.1, 0.2, 0.7],
        ]
        value = RocAucMetric().compute(y_true, y_pred, y_proba)
        assert 0.0 <= value <= 1.0


class TestRegressionMetrics:
    y_true = [3.0, -0.5, 2.0, 7.0]
    y_pred = [2.5, 0.0, 2.0, 8.0]

    def test_mae(self) -> None:
        assert MaeMetric().compute(self.y_true, self.y_pred) == pytest.approx(0.5)

    def test_mse(self) -> None:
        assert MseMetric().compute(self.y_true, self.y_pred) == pytest.approx(0.375)

    def test_rmse_is_the_square_root_of_mse(self) -> None:
        mse = MseMetric().compute(self.y_true, self.y_pred)
        assert RmseMetric().compute(self.y_true, self.y_pred) == pytest.approx(math.sqrt(mse))

    def test_r2(self) -> None:
        value = R2Metric().compute(self.y_true, self.y_pred)
        assert value <= 1.0

    def test_metadata_declares_direction(self) -> None:
        for metric in (MaeMetric(), MseMetric(), RmseMetric()):
            assert metric.metadata.higher_is_better is False
            assert metric.metadata.category == "regression"
        assert R2Metric().metadata.higher_is_better is True
