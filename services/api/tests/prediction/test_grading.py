"""Unit tests for `app.prediction.grading` — pure, no database.

Uses real `TargetPipeline`/`MetricRegistry` instances (the exact ones the
application wires everywhere else), not stubs — grading is only meaningful
if it reuses the identical target-generation logic that produced training
labels, so these tests prove that reuse against the real built-in target
generators and metrics, not a hand-rolled stand-in for either.
"""

import pytest

from app.evaluation.metrics import load_builtin_metrics
from app.evaluation.registry import default_registry as default_metric_registry
from app.ml_datasets.errors import InsufficientTargetDataError
from app.ml_datasets.pipeline import TargetPipeline
from app.ml_datasets.registry import default_registry as default_target_registry
from app.prediction.grading import grade_one
from tests.ml_datasets.conftest import candles


def _load_targets() -> None:
    # Mirrors `app.dependencies.ml_datasets.get_target_pipeline`'s own
    # `load_builtin_targets()` call, without needing the FastAPI dependency
    # layer for a pure-logic test.
    from app.ml_datasets.targets import load_builtin_targets

    load_builtin_targets()


def build_pipeline() -> TargetPipeline:
    _load_targets()
    return TargetPipeline(default_target_registry)


def build_metrics():
    load_builtin_metrics()
    return default_metric_registry


class TestGradeOneClassification:
    def test_a_correct_direction_prediction_is_marked_correct(self) -> None:
        # candles() closes are strictly increasing (100, 101, 102, ...), so
        # the real next_direction_1 outcome for row 0 is always "up".
        outcome = grade_one(
            target_name="next_direction",
            target_params={"horizon": "1"},
            target_column="next_direction_1",
            predicted_value="up",
            model_kind="classification",
            candles=candles(2),
            target_pipeline=build_pipeline(),
            metric_registry=build_metrics(),
        )

        assert outcome is not None
        assert outcome.actual_outcome == "up"
        assert outcome.is_correct is True
        assert outcome.error is None

    def test_an_incorrect_direction_prediction_is_marked_incorrect(self) -> None:
        outcome = grade_one(
            target_name="next_direction",
            target_params={"horizon": "1"},
            target_column="next_direction_1",
            predicted_value="down",
            model_kind="classification",
            candles=candles(2),
            target_pipeline=build_pipeline(),
            metric_registry=build_metrics(),
        )

        assert outcome is not None
        assert outcome.actual_outcome == "up"
        assert outcome.is_correct is False
        assert outcome.error is None

    def test_a_larger_horizon_looks_the_correct_number_of_candles_ahead(self) -> None:
        # candles(4): closes 100,101,102,103 — from row 0, 3 candles ahead
        # (index 3, close=103) is still higher than row 0's own close (100).
        outcome = grade_one(
            target_name="next_direction",
            target_params={"horizon": "3"},
            target_column="next_direction_3",
            predicted_value="up",
            model_kind="classification",
            candles=candles(4),
            target_pipeline=build_pipeline(),
            metric_registry=build_metrics(),
        )

        assert outcome is not None
        assert outcome.actual_outcome == "up"
        assert outcome.is_correct is True


class TestGradeOneRegression:
    def test_error_is_the_absolute_difference_reusing_the_mae_metric(self) -> None:
        # candles() closes are start_price + i; next_close_1 for row 0 of a
        # 2-row series is candles[1].close == 101.0.
        outcome = grade_one(
            target_name="next_close",
            target_params={"horizon": "1"},
            target_column="next_close_1",
            predicted_value=98.5,
            model_kind="regression",
            candles=candles(2),
            target_pipeline=build_pipeline(),
            metric_registry=build_metrics(),
        )

        assert outcome is not None
        assert outcome.actual_outcome == 101.0
        assert outcome.error == 2.5  # abs(101.0 - 98.5), the same MAE metric would compute
        assert outcome.is_correct is None

    def test_a_perfect_prediction_has_zero_error(self) -> None:
        outcome = grade_one(
            target_name="next_close",
            target_params={"horizon": "1"},
            target_column="next_close_1",
            predicted_value=101.0,
            model_kind="regression",
            candles=candles(2),
            target_pipeline=build_pipeline(),
            metric_registry=build_metrics(),
        )

        assert outcome is not None
        assert outcome.error == 0.0


class TestGradeOneReusesTheExactMetric:
    def test_is_correct_matches_the_registrys_own_accuracy_metric(self) -> None:
        """Not a hand-rolled `==` check: proves `is_correct` is exactly what
        `AccuracyMetric.compute` itself returns for this one-element pair."""
        registry = build_metrics()
        accuracy = registry.get("accuracy")

        outcome = grade_one(
            target_name="next_direction",
            target_params={"horizon": "1"},
            target_column="next_direction_1",
            predicted_value="up",
            model_kind="classification",
            candles=candles(2),
            target_pipeline=build_pipeline(),
            metric_registry=registry,
        )

        assert outcome is not None
        expected = accuracy.compute([outcome.actual_outcome], ["up"]) == 1.0
        assert outcome.is_correct is expected

    def test_error_matches_the_registrys_own_mae_metric(self) -> None:
        """Not a hand-rolled `abs()`: proves `error` is exactly what
        `MaeMetric.compute` itself returns for this one-element pair."""
        registry = build_metrics()
        mae = registry.get("mae")

        outcome = grade_one(
            target_name="next_close",
            target_params={"horizon": "1"},
            target_column="next_close_1",
            predicted_value=98.5,
            model_kind="regression",
            candles=candles(2),
            target_pipeline=build_pipeline(),
            metric_registry=registry,
        )

        assert outcome is not None
        expected = mae.compute([outcome.actual_outcome], [98.5])
        assert outcome.error == expected


class TestGradeOneEdgeCases:
    def test_returns_none_for_an_unknown_model_kind(self) -> None:
        """Outcome is still determined; correctness assessment is simply not
        attempted for a `model_kind` that is neither classifier nor regressor."""
        outcome = grade_one(
            target_name="next_direction",
            target_params={"horizon": "1"},
            target_column="next_direction_1",
            predicted_value="up",
            model_kind="unknown",
            candles=candles(2),
            target_pipeline=build_pipeline(),
            metric_registry=build_metrics(),
        )

        assert outcome is not None
        assert outcome.actual_outcome == "up"
        assert outcome.is_correct is None
        assert outcome.error is None

    def test_returns_none_when_no_series_matches_the_target_column(self) -> None:
        outcome = grade_one(
            target_name="next_direction",
            target_params={"horizon": "1"},
            target_column="not_a_real_column",
            predicted_value="up",
            model_kind="classification",
            candles=candles(2),
            target_pipeline=build_pipeline(),
            metric_registry=build_metrics(),
        )

        assert outcome is None

    def test_propagates_insufficient_candle_errors_rather_than_silently_grading_wrong(
        self,
    ) -> None:
        """Grading never decides gradeability itself (see the module's own
        docstring) — a caller that hands it too few candles gets the exact
        same `InsufficientTargetDataError` `TargetPipeline.run` always
        raises, not a silently wrong answer."""
        with pytest.raises(InsufficientTargetDataError):
            grade_one(
                target_name="next_direction",
                target_params={"horizon": "5"},
                target_column="next_direction_5",
                predicted_value="up",
                model_kind="classification",
                candles=candles(2),  # fewer than horizon(5) + 1
                target_pipeline=build_pipeline(),
                metric_registry=build_metrics(),
            )
