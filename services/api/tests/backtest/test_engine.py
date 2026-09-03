"""Unit tests for `app.backtest.engine` — the two pure computations genuinely
new to the Backtesting Engine: planning a capped walk, and aggregating
graded rows via the *existing* `EvaluationEngine`, never a reimplementation.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.backtest.base import GradedPredictionRow
from app.backtest.engine import aggregate, plan_steps
from app.backtest.errors import InvalidBacktestRangeError
from app.evaluation.metrics import load_builtin_metrics

load_builtin_metrics()

BASE = datetime(2026, 1, 1, tzinfo=UTC)


class TestPlanSteps:
    def test_walks_every_step_in_a_range_that_divides_evenly(self) -> None:
        plan = plan_steps(
            start=BASE,
            end=BASE + timedelta(hours=5),
            step_interval=timedelta(hours=1),
            max_steps=100,
        )

        assert plan.as_of_values == [BASE + timedelta(hours=i) for i in range(5)]
        assert plan.effective_end == BASE + timedelta(hours=5)
        assert plan.truncated is False
        assert plan.requested_steps == 5

    def test_caps_a_range_that_needs_more_steps_than_allowed_from_the_end(self) -> None:
        """Truncation keeps the *earliest* steps and cuts the tail — the same
        direction `MAX_REPLAY_CANDLES` already truncates from."""
        plan = plan_steps(
            start=BASE,
            end=BASE + timedelta(hours=10),
            step_interval=timedelta(hours=1),
            max_steps=3,
        )

        assert plan.as_of_values == [BASE, BASE + timedelta(hours=1), BASE + timedelta(hours=2)]
        assert plan.effective_end == BASE + timedelta(hours=3)
        assert plan.truncated is True
        assert plan.requested_steps == 10  # the honest, uncapped count

    def test_does_not_report_truncation_when_the_range_exactly_fits_max_steps(self) -> None:
        plan = plan_steps(
            start=BASE,
            end=BASE + timedelta(hours=3),
            step_interval=timedelta(hours=1),
            max_steps=3,
        )

        assert len(plan.as_of_values) == 3
        assert plan.truncated is False
        assert plan.requested_steps == 3

    def test_a_partial_final_step_still_counts_as_a_whole_step(self) -> None:
        """A 90-minute range at a 1h step needs a 2nd (partial) step to cover
        it — `ceil`, not floor, so the walk never silently drops it."""
        plan = plan_steps(
            start=BASE,
            end=BASE + timedelta(minutes=90),
            step_interval=timedelta(hours=1),
            max_steps=100,
        )

        assert plan.as_of_values == [BASE, BASE + timedelta(hours=1)]
        assert plan.requested_steps == 2

    def test_rejects_an_empty_or_backwards_range(self) -> None:
        with pytest.raises(InvalidBacktestRangeError):
            plan_steps(start=BASE, end=BASE, step_interval=timedelta(hours=1), max_steps=10)
        with pytest.raises(InvalidBacktestRangeError):
            plan_steps(
                start=BASE,
                end=BASE - timedelta(hours=1),
                step_interval=timedelta(hours=1),
                max_steps=10,
            )


class TestAggregate:
    def test_classification_accuracy_matches_a_hand_count_of_correct_rows(self) -> None:
        """4 rows, 3 correct (idx 0, 1, 3) and 1 wrong (idx 2) — accuracy is
        exactly 3/4, independently countable by inspection, not re-derived
        from the engine itself."""
        rows = [
            GradedPredictionRow(
                predicted_value="up", actual_outcome="up", classes=None, probabilities=None
            ),
            GradedPredictionRow(
                predicted_value="down", actual_outcome="down", classes=None, probabilities=None
            ),
            GradedPredictionRow(
                predicted_value="down", actual_outcome="up", classes=None, probabilities=None
            ),
            GradedPredictionRow(
                predicted_value="down", actual_outcome="down", classes=None, probabilities=None
            ),
        ]

        report = aggregate("classification", rows)

        assert report.metrics["accuracy"] == pytest.approx(0.75)
        # No row carries probabilities -> roc_auc gracefully skipped, not fabricated.
        assert "roc_auc" not in report.metrics
        assert "roc_auc" in report.skipped

    def test_regression_mae_matches_a_hand_computed_average_absolute_error(self) -> None:
        """|10-12| + |20-18| + |30-33| = 2 + 2 + 3 = 7, over 3 rows -> 7/3."""
        rows = [
            GradedPredictionRow(
                predicted_value=12.0, actual_outcome=10.0, classes=None, probabilities=None
            ),
            GradedPredictionRow(
                predicted_value=18.0, actual_outcome=20.0, classes=None, probabilities=None
            ),
            GradedPredictionRow(
                predicted_value=33.0, actual_outcome=30.0, classes=None, probabilities=None
            ),
        ]

        report = aggregate("regression", rows)

        assert report.metrics["mae"] == pytest.approx(7 / 3)

    def test_reconstructs_ordered_probabilities_only_when_every_row_has_them(self) -> None:
        """A mix of classifier rows with and without probabilities (e.g. a
        target column change never happens in practice, but the contract
        must hold defensively) must never fabricate a probability row for
        the ones missing it — `y_proba` stays `None` entirely rather than
        partially filled."""
        with_proba = GradedPredictionRow(
            predicted_value="up",
            actual_outcome="up",
            classes=["down", "up"],
            probabilities={"down": 0.2, "up": 0.8},
        )
        without_proba = GradedPredictionRow(
            predicted_value="down", actual_outcome="down", classes=None, probabilities=None
        )

        report = aggregate("classification", [with_proba, without_proba])

        assert "roc_auc" not in report.metrics
        assert "roc_auc" in report.skipped

    def test_computes_roc_auc_when_every_row_carries_probabilities(self) -> None:
        rows = [
            GradedPredictionRow(
                predicted_value="up",
                actual_outcome="up",
                classes=["down", "up"],
                probabilities={"down": 0.1, "up": 0.9},
            ),
            GradedPredictionRow(
                predicted_value="down",
                actual_outcome="down",
                classes=["down", "up"],
                probabilities={"down": 0.8, "up": 0.2},
            ),
            GradedPredictionRow(
                predicted_value="up",
                actual_outcome="down",
                classes=["down", "up"],
                probabilities={"down": 0.3, "up": 0.7},
            ),
            GradedPredictionRow(
                predicted_value="down",
                actual_outcome="up",
                classes=["down", "up"],
                probabilities={"down": 0.6, "up": 0.4},
            ),
        ]

        report = aggregate("classification", rows)

        assert "roc_auc" in report.metrics
        assert 0.0 <= report.metrics["roc_auc"] <= 1.0

    def test_an_empty_row_set_produces_an_empty_report_not_an_error(self) -> None:
        report = aggregate("classification", [])
        assert report.metrics == {}
