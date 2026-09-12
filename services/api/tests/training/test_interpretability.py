"""Tests for `app/training/interpretability.py`'s pure evaluation/interpretability helpers.

Exercised directly (no database, no adapter) since every function here is pure —
`logistic_regression.py`/`linear_regression.py` already exercise these indirectly
end-to-end, but these tests pin each function's own contract precisely, including
edge cases (a "low" confidence probability, a not-flagged overfitting gap, a neutral
sign) real training runs don't happen to produce.
"""

import numpy as np
import pytest
from numpy.typing import NDArray

from app.training.interpretability import (
    build_prediction_samples,
    compute_confusion_details,
    compute_feature_importance,
    compute_impurity_feature_importance,
    compute_overfitting_flag,
    compute_permutation_importance,
    compute_roc_pr_curves,
    confidence_level,
    to_float_list,
    to_int_list,
)


class _FakeArray:
    """Stands in for the numpy array a scikit-learn call would return, but with a
    `tolist()` that yields whatever a test needs — including deliberately
    wrong-shaped output, to exercise the narrowing helpers' guard clauses."""

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def tolist(self) -> object:
        return self._payload


class TestNarrowingHelperGuards:
    """The defensive `raise TypeError` branches in the private `_ensure_array` /
    `_as_list` / `_as_float` / `_as_int` narrowing helpers, reached through the
    public `to_*` functions — see the module's `NumpyArrayLike` docstring for why
    these guards exist rather than trusting scikit-learn's (absent) type info."""

    def test_ensure_array_rejects_a_value_without_tolist(self) -> None:
        with pytest.raises(TypeError, match="array-like"):
            to_float_list(object())

    def test_as_list_rejects_tolist_output_that_is_not_a_list(self) -> None:
        with pytest.raises(TypeError, match="array-like"):
            to_float_list(_FakeArray(5))

    def test_as_float_rejects_a_non_numeric_element(self) -> None:
        with pytest.raises(TypeError, match="numeric array element"):
            to_float_list(_FakeArray(["not a number"]))

    def test_as_int_rejects_a_non_numeric_element(self) -> None:
        with pytest.raises(TypeError, match="numeric array element"):
            to_int_list(_FakeArray(["not a number"]))


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
            {
                "feature": "x",
                "coefficient": 0.0,
                "abs_importance": 0.0,
                "sign": "neutral",
                "normalized": False,
            },
            {
                "feature": "y",
                "coefficient": 0.0,
                "abs_importance": 0.0,
                "sign": "neutral",
                "normalized": False,
            },
        ]

    def test_defaults_every_row_to_not_normalized(self) -> None:
        rows = compute_feature_importance(["a"], [[1.0]])

        assert rows[0]["normalized"] is False

    def test_tags_every_row_as_normalized_when_requested(self) -> None:
        rows = compute_feature_importance(["a", "b"], [[1.0, -2.0]], normalized=True)

        assert all(row["normalized"] is True for row in rows)

    def test_ranking_flips_between_raw_and_normalized_coefficients_for_differently_scaled_features(
        self,
    ) -> None:
        """The concrete scenario this platform's scale bias actually produces: a
        `close`-scale feature (thousands) needs only a tiny raw coefficient to
        matter as much as a `candle_body`-scale feature (single digits) needs a
        much larger one for the identical real contribution — so ranking by raw
        coefficient magnitude alone says `candle_body` is more important, and
        ranking by the *normalized*-space coefficient (which cancels the scale
        difference out) says the opposite."""
        # Raw fit: close's coefficient is tiny (it needs to be, at its scale) —
        # 0.0008 * ~1000 and 0.3 * ~2 both describe roughly the same real
        # contribution to the decision boundary, just expressed very differently.
        raw_rows = compute_feature_importance(["close", "candle_body"], [[0.0008, 0.3]])
        raw_ranking = [
            row["feature"] for row in sorted(raw_rows, key=lambda r: -r["abs_importance"])
        ]
        assert raw_ranking == ["candle_body", "close"]

        # Normalized-space coefficients for the identical underlying model (each
        # raw coefficient scaled by its own column's std — the standard
        # relationship between a raw and a z-scored coefficient): close's
        # std ~1000 -> 0.0008*1000=0.8; candle_body's std ~2 -> 0.3*2=0.6.
        normalized_rows = compute_feature_importance(
            ["close", "candle_body"], [[0.8, 0.6]], normalized=True
        )
        normalized_ranking = [
            row["feature"] for row in sorted(normalized_rows, key=lambda r: -r["abs_importance"])
        ]
        assert normalized_ranking == ["close", "candle_body"]

        # The whole point: the two rankings disagree, and only the normalized
        # one is scale-comparable — each row says so explicitly.
        assert raw_ranking != normalized_ranking
        assert all(row["normalized"] is False for row in raw_rows)
        assert all(row["normalized"] is True for row in normalized_rows)


class TestComputeImpurityFeatureImportance:
    def test_ranks_by_importance_descending_with_neutral_signs(self) -> None:
        rows = compute_impurity_feature_importance(["a", "b", "c"], [0.1, 0.7, 0.2])

        assert [row["feature"] for row in rows] == ["b", "c", "a"]
        assert all(row["sign"] == "neutral" for row in rows)
        assert rows[0]["abs_importance"] == pytest.approx(0.7)
        assert rows[0]["coefficient"] == pytest.approx(0.7)

    def test_defaults_to_not_normalized_and_tags_when_requested(self) -> None:
        assert compute_impurity_feature_importance(["a"], [1.0])[0]["normalized"] is False
        tagged = compute_impurity_feature_importance(["a", "b"], [0.4, 0.6], normalized=True)
        assert all(row["normalized"] is True for row in tagged)

    def test_pairs_only_up_to_the_shorter_of_columns_and_importances(self) -> None:
        # Defensive: a caller passing mismatched lengths gets the safe intersection,
        # never an IndexError.
        rows = compute_impurity_feature_importance(["a", "b", "c"], [0.5, 0.5])

        assert {row["feature"] for row in rows} == {"a", "b"}

    def test_empty_inputs_produce_no_rows(self) -> None:
        assert compute_impurity_feature_importance([], []) == []


class TestComputePermutationImportance:
    """Exercised against a real, cheaply-fitted scikit-learn model (a decision
    tree) rather than a mock — `sklearn.inspection.permutation_importance`
    itself calls `model.predict`/`model.score`, so a fake with the right
    shape would only prove this function calls *something*, not that it
    calls a real scikit-learn estimator correctly."""

    def _fit_signal_vs_noise(self) -> tuple[object, NDArray[np.float64], list[str]]:
        from sklearn.tree import DecisionTreeClassifier

        # Same "signal vs. noise" fixture shape as the adapter tests: the
        # first feature perfectly determines the label, the second is pure
        # noise the model should learn to ignore. A real `numpy.ndarray`,
        # not a plain nested list — the same conversion every real adapter
        # does at the one seam it actually needs one (`np.asarray(dataset
        # .train.X)`), which `.fit()`/`permutation_importance` both expect.
        X = np.asarray([[float(i), float(i % 5)] for i in range(-40, 40)])  # noqa: N806
        y = ["pos" if row[0] > 0 else "neg" for row in X]
        model = DecisionTreeClassifier(random_state=0).fit(X, y)
        return model, X, y

    def test_ranks_the_real_signal_feature_above_pure_noise(self) -> None:
        model, X, y = self._fit_signal_vs_noise()  # noqa: N806

        rows = compute_permutation_importance(["signal", "noise"], model, X, y, random_state=0)

        assert [row["feature"] for row in rows] == ["signal", "noise"]
        assert rows[0]["abs_importance"] > rows[1]["abs_importance"]
        assert rows[0]["abs_importance"] > 0

    def test_signs_are_always_neutral_unlike_a_linear_coefficient(self) -> None:
        model, X, y = self._fit_signal_vs_noise()  # noqa: N806

        rows = compute_permutation_importance(["signal", "noise"], model, X, y, random_state=0)

        assert all(row["sign"] == "neutral" for row in rows)

    def test_defaults_to_not_normalized_and_tags_when_requested(self) -> None:
        model, X, y = self._fit_signal_vs_noise()  # noqa: N806

        assert (
            compute_permutation_importance(["signal", "noise"], model, X, y)[0]["normalized"]
            is False
        )
        tagged = compute_permutation_importance(["signal", "noise"], model, X, y, normalized=True)
        assert all(row["normalized"] is True for row in tagged)

    def test_two_calls_with_the_same_seed_are_identical(self) -> None:
        model, X, y = self._fit_signal_vs_noise()  # noqa: N806

        first = compute_permutation_importance(["signal", "noise"], model, X, y, random_state=5)
        second = compute_permutation_importance(["signal", "noise"], model, X, y, random_state=5)

        assert first == second

    def test_a_model_with_no_predictive_power_at_all_ranks_near_zero(self) -> None:
        from sklearn.dummy import DummyClassifier

        # A constant-predicting model: shuffling any feature cannot change its
        # (already input-independent) predictions, so every importance should
        # sit at exactly zero — the same "no decision skill -> zero
        # permutation importance" signature the horizon-sweep research
        # documented for a real near-constant model.
        X = np.asarray([[float(i), float(i % 5)] for i in range(-20, 20)])  # noqa: N806
        y = ["pos" if row[0] > 0 else "neg" for row in X]
        model = DummyClassifier(strategy="most_frequent").fit(X, y)

        rows = compute_permutation_importance(["signal", "noise"], model, X, y, random_state=0)

        assert all(row["abs_importance"] == pytest.approx(0.0) for row in rows)


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
