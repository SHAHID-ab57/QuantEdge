"""Tests for `app/training/interpretability.py`'s pure evaluation/interpretability helpers.

Exercised directly (no database, no adapter) since every function here is pure —
`logistic_regression.py`/`linear_regression.py` already exercise these indirectly
end-to-end, but these tests pin each function's own contract precisely, including
edge cases (a "low" confidence probability, a not-flagged overfitting gap, a neutral
sign) real training runs don't happen to produce.
"""

import pytest

from app.training.interpretability import (
    build_prediction_samples,
    compute_confusion_details,
    compute_feature_importance,
    compute_overfitting_flag,
    compute_roc_pr_curves,
    confidence_level,
)


class TestConfidenceLevel:
    def test_high_at_or_above_0_7(self) -> None:
        assert confidence_level(0.7) == "high"
        assert confidence_level(0.95) == "high"

    def test_medium_between_0_5_and_0_7(self) -> None:
        assert confidence_level(0.5) == "medium"
        assert confidence_level(0.69) == "medium"

    def test_low_below_0_5(self) -> None:
        assert confidence_level(0.49) == "low"
        assert confidence_level(0.0) == "low"


class TestComputeFeatureImportance:
    def test_ranks_by_absolute_magnitude_descending(self) -> None:
        rows = compute_feature_importance(["a", "b", "c"], [[0.1, -0.9, 0.3]])

        assert [row["feature"] for row in rows] == ["b", "c", "a"]
        assert rows[0]["sign"] == "negative"
        assert rows[1]["sign"] == "positive"

    def test_averages_across_multiple_classes(self) -> None:
        # Two classes' coefficients for the same feature: +1.0 and -1.0 average to a
        # neutral sign but a non-zero absolute importance (mean of absolute values).
        rows = compute_feature_importance(["x"], [[1.0], [-1.0]])

        assert rows[0]["sign"] == "neutral"
        assert rows[0]["coefficient"] == 0.0
        assert rows[0]["abs_importance"] == 1.0

    def test_handles_no_coefficient_rows_without_dividing_by_zero(self) -> None:
        rows = compute_feature_importance(["x", "y"], [])

        assert rows == [
            {"feature": "x", "coefficient": 0.0, "abs_importance": 0.0, "sign": "neutral"},
            {"feature": "y", "coefficient": 0.0, "abs_importance": 0.0, "sign": "neutral"},
        ]


class TestComputeConfusionDetails:
    def test_reports_tp_fp_tn_fn_and_support_per_class(self) -> None:
        y_true = ["up", "up", "down", "down", "flat"]
        y_pred = ["up", "down", "down", "down", "flat"]

        details = compute_confusion_details(y_true, y_pred, ["up", "down", "flat"])
        by_class = {row["class"]: row for row in details}

        assert by_class["up"]["true_positive"] == 1
        assert by_class["up"]["false_negative"] == 1
        assert by_class["up"]["support"] == 2
        assert by_class["down"]["true_positive"] == 2
        assert by_class["down"]["false_positive"] == 1
        assert by_class["flat"]["true_positive"] == 1
        assert by_class["flat"]["support"] == 1


class TestComputeRocPrCurves:
    def test_binary_case_produces_a_curve_and_auc_for_both_classes(self) -> None:
        y_true = ["up", "up", "down", "down"]
        y_proba = [[0.2, 0.8], [0.4, 0.6], [0.7, 0.3], [0.9, 0.1]]

        result = compute_roc_pr_curves(y_true, y_proba, ["down", "up"])

        assert set(result["curves"]) == {"down", "up"}
        assert 0.0 <= result["auc"]["up"] <= 1.0
        assert result["auc"]["up"] == 1.0  # perfectly separable by score above
        assert result["macro_auc"] is not None

    def test_multiclass_case_computes_one_curve_per_class(self) -> None:
        y_true = ["up", "down", "flat", "up", "down", "flat"]
        y_proba = [
            [0.7, 0.2, 0.1],
            [0.1, 0.8, 0.1],
            [0.1, 0.1, 0.8],
            [0.6, 0.3, 0.1],
            [0.2, 0.7, 0.1],
            [0.2, 0.1, 0.7],
        ]

        result = compute_roc_pr_curves(y_true, y_proba, ["up", "down", "flat"])

        assert set(result["curves"]) == {"up", "down", "flat"}
        assert set(result["auc"]) == {"up", "down", "flat"}
        assert set(result["average_precision"]) == {"up", "down", "flat"}


class TestBuildPredictionSamples:
    def test_classification_samples_include_probability_confidence_and_correctness(
        self,
    ) -> None:
        samples = build_prediction_samples(
            actual=["up", "down"],
            predicted=["up", "up"],
            probabilities=[[0.1, 0.9], [0.6, 0.4]],
            classes=["down", "up"],
        )

        assert samples[0]["correct"] is True
        assert samples[0]["confidence_level"] == "high"
        assert samples[1]["correct"] is False
        assert samples[1]["confidence_level"] == "medium"

    def test_regression_samples_have_no_probability_confidence_or_correctness(self) -> None:
        samples = build_prediction_samples(actual=[1.0, 2.0], predicted=[1.1, 1.9])

        assert samples == [
            {
                "actual": 1.0,
                "predicted": 1.1,
                "probability": None,
                "confidence_level": None,
                "correct": None,
            },
            {
                "actual": 2.0,
                "predicted": 1.9,
                "probability": None,
                "confidence_level": None,
                "correct": None,
            },
        ]

    def test_caps_the_number_of_samples_returned(self) -> None:
        actual = list(range(100))
        predicted = list(range(100))

        samples = build_prediction_samples(actual=actual, predicted=predicted, cap=5)

        assert len(samples) == 5


class TestComputeOverfittingFlag:
    def test_flags_a_large_gap_when_higher_is_better(self) -> None:
        result = compute_overfitting_flag(0.99, 0.5, higher_is_better=True)

        assert result["flagged"] is True
        assert result["gap"] == pytest.approx(0.49)

    def test_does_not_flag_a_small_gap(self) -> None:
        result = compute_overfitting_flag(0.85, 0.80, higher_is_better=True)

        assert result["flagged"] is False

    def test_flags_error_style_metrics_in_the_opposite_direction(self) -> None:
        # For MAE/MSE (lower is better), overfitting shows up as the held-out error
        # being much *higher* than the train error.
        result = compute_overfitting_flag(0.01, 0.50, higher_is_better=False)

        assert result["flagged"] is True
