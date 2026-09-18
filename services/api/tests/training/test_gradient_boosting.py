"""Tests for `GradientBoostingAdapter` — a real scikit-learn boosted-tree classifier.

Mirrors `test_random_forest.py`'s coverage depth: initialize, the
no-real-data and scikit-learn-failure error paths, a real fit reporting
exact metrics on separable data, hyperparameter recording, predict, and
the adapter-specific piece — permutation feature importances (unsigned,
ranked, measured against validation, not train).
"""

from pathlib import Path

import pytest

import app.training.adapters.gradient_boosting as gradient_boosting_module
from app.training.adapters.gradient_boosting import GradientBoostingAdapter
from app.training.base import SplitMatrix, TrainingDataset
from app.training.errors import TrainingExecutionError
from app.training.serialization import LocalDiskModelSerializer


def make_dataset() -> TrainingDataset:
    # Deterministic, perfectly separable-by-sign data: label is "pos" when the
    # first feature is positive, "neg" otherwise; the second feature is pure
    # noise. A boosted-tree ensemble should learn the split trivially, so
    # metrics are exact and the noise feature should rank far below the
    # signal feature under permutation importance. Larger than the RF
    # adapter's own fixture (80 vs. 40 train rows) — HistGradientBoosting's
    # default min_samples_leaf=20 needs enough rows per class to actually
    # split on the signal feature at all.
    train_x = [[float(i), float(i % 5)] for i in range(-40, 40)]
    train_y = ["pos" if x[0] > 0 else "neg" for x in train_x]
    validation_x = [[5.0, 1.0], [-5.0, 2.0], [3.0, 0.0], [-3.0, 4.0]]
    validation_y = ["pos", "neg", "pos", "neg"]
    test_x = [[1.0, 3.0], [-1.0, 0.0]]
    test_y = ["pos", "neg"]
    return TrainingDataset(
        dataset_version="ds-test",
        feature_columns=("signal", "noise"),
        target_column="label",
        train=SplitMatrix(X=train_x, y=train_y),
        validation=SplitMatrix(X=validation_x, y=validation_y),
        test=SplitMatrix(X=test_x, y=test_y),
    )


@pytest.fixture(autouse=True)
def _local_serializer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirects the adapter module's `default_serializer` to a throwaway directory,
    so every test in this file writes/reads joblib artifacts under `tmp_path`
    instead of the process-wide `Settings.model_artifact_dir`."""
    monkeypatch.setattr(
        gradient_boosting_module, "default_serializer", LocalDiskModelSerializer(tmp_path)
    )


class TestInitialize:
    def test_accepts_valid_hyperparameters(self) -> None:
        GradientBoostingAdapter().initialize(
            {
                "max_iter": 50,
                "max_depth": 4,
                "learning_rate": 0.05,
                "min_samples_leaf": 5,
                "random_seed": 1,
            }
        )

    def test_uses_defaults_when_omitted(self) -> None:
        GradientBoostingAdapter().initialize({})

    def test_accepts_none_max_depth(self) -> None:
        GradientBoostingAdapter().initialize({"max_depth": None})


class TestTrain:
    def test_raises_when_no_real_data_is_loaded(self) -> None:
        adapter = GradientBoostingAdapter()
        with pytest.raises(TrainingExecutionError):
            adapter.train(TrainingDataset(dataset_version="ds-1"), {})

    def test_wraps_a_scikit_learn_fit_failure_as_a_training_execution_error(self) -> None:
        adapter = GradientBoostingAdapter()
        broken = TrainingDataset(
            dataset_version="ds-1",
            feature_columns=("x",),
            target_column="label",
            # Mismatched X/y row counts — scikit-learn raises ValueError on `.fit`.
            train=SplitMatrix(X=[[1.0], [2.0]], y=["pos"]),
            validation=SplitMatrix(X=[[1.0]], y=["pos"]),
        )

        with pytest.raises(TrainingExecutionError):
            adapter.train(broken, {})

    def test_trains_and_reports_perfect_metrics_on_separable_data(self) -> None:
        adapter = GradientBoostingAdapter()

        result = adapter.train(make_dataset(), {"max_iter": 50})

        assert result.metrics["accuracy"] == pytest.approx(1.0)
        assert result.metrics["f1"] == pytest.approx(1.0)
        assert not result.artifact_uri.startswith("file://")  # bare relative filename now
        assert result.artifact_uri.endswith(".joblib")
        assert set(result.summary["classes"]) == {"neg", "pos"}
        assert result.summary["target_column"] == "label"
        assert result.summary["feature_columns"] == ["signal", "noise"]
        assert result.summary["n_train"] == 80
        assert result.summary["n_validation"] == 4
        assert result.summary["n_test"] == 2
        assert "confusion_matrix" in result.summary
        assert "roc_pr_curves" in result.summary
        assert result.summary["test_metrics"]["accuracy"] == pytest.approx(1.0)

    def test_feature_importance_method_is_recorded_as_permutation(self) -> None:
        adapter = GradientBoostingAdapter()

        result = adapter.train(make_dataset(), {"max_iter": 50})

        assert result.summary["feature_importance_method"] == "permutation"

    def test_feature_importances_are_unsigned_and_rank_signal_above_noise(self) -> None:
        adapter = GradientBoostingAdapter()

        result = adapter.train(make_dataset(), {"max_iter": 50})

        importance = result.summary["feature_importance"]
        # Ranked descending by importance, and the real signal feature
        # dominates the pure-noise one.
        assert [row["feature"] for row in importance] == ["signal", "noise"]
        assert importance[0]["abs_importance"] > importance[1]["abs_importance"]
        # Permutation importance has no direction — unlike a linear coefficient.
        assert all(row["sign"] == "neutral" for row in importance)
        assert all(row["normalized"] is False for row in importance)

    def test_hyperparameters_are_recorded_in_the_summary(self) -> None:
        adapter = GradientBoostingAdapter()

        result = adapter.train(
            make_dataset(),
            {
                "max_iter": 30,
                "max_depth": 5,
                "learning_rate": 0.2,
                "min_samples_leaf": 4,
                "random_seed": 7,
            },
        )

        assert result.summary["hyperparameters"] == {
            "max_iter": 30,
            "max_depth": 5,
            "learning_rate": 0.2,
            "min_samples_leaf": 4,
            "random_seed": 7,
        }

    def test_defaults_are_the_documented_values(self) -> None:
        adapter = GradientBoostingAdapter()

        result = adapter.train(make_dataset(), {})

        assert result.summary["hyperparameters"] == {
            "max_iter": 200,
            "max_depth": 6,
            "learning_rate": 0.1,
            "min_samples_leaf": 20,
            "random_seed": 42,
        }

    def test_two_runs_with_the_same_seed_are_identical(self) -> None:
        first = GradientBoostingAdapter().train(make_dataset(), {"max_iter": 25, "random_seed": 3})
        second = GradientBoostingAdapter().train(make_dataset(), {"max_iter": 25, "random_seed": 3})

        assert first.summary["feature_importance"] == second.summary["feature_importance"]
        assert first.metrics == second.metrics


class TestPredict:
    def test_loads_the_saved_model_and_predicts(self) -> None:
        adapter = GradientBoostingAdapter()
        result = adapter.train(make_dataset(), {"max_iter": 25})

        predictions = adapter.predict(result.artifact_uri, [[5.0, 1.0], [-5.0, 2.0]])

        assert predictions == ["pos", "neg"]

    def test_predict_proba_returns_one_row_per_input_with_a_column_per_class(self) -> None:
        adapter = GradientBoostingAdapter()
        result = adapter.train(make_dataset(), {"max_iter": 25})

        probabilities = adapter.predict_proba(result.artifact_uri, [[5.0, 1.0], [-5.0, 2.0]])

        assert probabilities is not None
        assert len(probabilities) == 2
        assert all(len(row) == 2 for row in probabilities)
        assert all(sum(row) == pytest.approx(1.0) for row in probabilities)
