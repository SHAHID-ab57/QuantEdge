"""Tests for `RandomForestAdapter` — a real scikit-learn ensemble classifier.

Mirrors `test_logistic_regression.py`'s coverage depth: initialize, the
no-real-data and scikit-learn-failure error paths, a real fit reporting exact
metrics on separable data, hyperparameter recording, predict, and the
adapter-specific piece — impurity feature importances (unsigned, ranked).
"""

from pathlib import Path

import pytest

import app.training.adapters.random_forest as random_forest_module
from app.training.adapters.random_forest import RandomForestAdapter
from app.training.base import SplitMatrix, TrainingDataset
from app.training.errors import TrainingExecutionError
from app.training.serialization import LocalDiskModelSerializer


def make_dataset() -> TrainingDataset:
    # Deterministic, perfectly separable-by-sign data: label is "pos" when the
    # first feature is positive, "neg" otherwise; the second feature is pure
    # noise. A tree ensemble should learn the split trivially, so metrics are
    # exact and the noise feature should rank far below the signal feature.
    train_x = [[float(i), float(i % 5)] for i in range(-20, 20)]
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
        random_forest_module, "default_serializer", LocalDiskModelSerializer(tmp_path)
    )


class TestInitialize:
    def test_accepts_valid_hyperparameters(self) -> None:
        RandomForestAdapter().initialize(
            {"n_estimators": 50, "max_depth": 4, "min_samples_leaf": 3, "random_seed": 1}
        )

    def test_uses_defaults_when_omitted(self) -> None:
        RandomForestAdapter().initialize({})

    def test_accepts_none_max_depth(self) -> None:
        RandomForestAdapter().initialize({"max_depth": None})


class TestTrain:
    def test_raises_when_no_real_data_is_loaded(self) -> None:
        adapter = RandomForestAdapter()
        with pytest.raises(TrainingExecutionError):
            adapter.train(TrainingDataset(dataset_version="ds-1"), {})

    def test_wraps_a_scikit_learn_fit_failure_as_a_training_execution_error(self) -> None:
        adapter = RandomForestAdapter()
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
        adapter = RandomForestAdapter()

        result = adapter.train(make_dataset(), {"n_estimators": 50})

        assert result.metrics["accuracy"] == pytest.approx(1.0)
        assert result.metrics["f1"] == pytest.approx(1.0)
        assert not result.artifact_uri.startswith("file://")  # bare relative filename now
        assert result.artifact_uri.endswith(".joblib")
        assert set(result.summary["classes"]) == {"neg", "pos"}
        assert result.summary["target_column"] == "label"
        assert result.summary["feature_columns"] == ["signal", "noise"]
        assert result.summary["n_train"] == 40
        assert result.summary["n_validation"] == 4
        assert result.summary["n_test"] == 2
        assert "confusion_matrix" in result.summary
        assert "roc_pr_curves" in result.summary
        assert result.summary["test_metrics"]["accuracy"] == pytest.approx(1.0)

    def test_feature_importances_are_unsigned_and_rank_signal_above_noise(self) -> None:
        adapter = RandomForestAdapter()

        result = adapter.train(make_dataset(), {"n_estimators": 50})

        importance = result.summary["feature_importance"]
        # Ranked descending by importance, and the real signal feature dominates
        # the pure-noise one.
        assert [row["feature"] for row in importance] == ["signal", "noise"]
        assert importance[0]["abs_importance"] > importance[1]["abs_importance"]
        # A tree ensemble's impurity importance has no direction.
        assert all(row["sign"] == "neutral" for row in importance)
        # Impurity importances are normalized to sum to 1 across features.
        assert sum(row["abs_importance"] for row in importance) == pytest.approx(1.0)
        assert all(row["normalized"] is False for row in importance)

    def test_hyperparameters_are_recorded_in_the_summary(self) -> None:
        adapter = RandomForestAdapter()

        result = adapter.train(
            make_dataset(),
            {"n_estimators": 30, "max_depth": 5, "min_samples_leaf": 4, "random_seed": 7},
        )

        assert result.summary["hyperparameters"] == {
            "n_estimators": 30,
            "max_depth": 5,
            "min_samples_leaf": 4,
            "max_features": "sqrt",
            "random_seed": 7,
        }

    def test_defaults_are_the_documented_modest_values(self) -> None:
        adapter = RandomForestAdapter()

        result = adapter.train(make_dataset(), {})

        assert result.summary["hyperparameters"] == {
            "n_estimators": 200,
            "max_depth": 8,
            "min_samples_leaf": 2,
            "max_features": "sqrt",
            "random_seed": 42,
        }

    def test_two_runs_with_the_same_seed_are_identical(self) -> None:
        first = RandomForestAdapter().train(make_dataset(), {"n_estimators": 25, "random_seed": 3})
        second = RandomForestAdapter().train(make_dataset(), {"n_estimators": 25, "random_seed": 3})

        assert first.summary["feature_importance"] == second.summary["feature_importance"]
        assert first.metrics == second.metrics


class TestPredict:
    def test_loads_the_saved_model_and_predicts(self) -> None:
        adapter = RandomForestAdapter()
        result = adapter.train(make_dataset(), {"n_estimators": 25})

        predictions = adapter.predict(result.artifact_uri, [[5.0, 1.0], [-5.0, 2.0]])

        assert predictions == ["pos", "neg"]

    def test_predict_proba_returns_one_row_per_input_with_a_column_per_class(self) -> None:
        adapter = RandomForestAdapter()
        result = adapter.train(make_dataset(), {"n_estimators": 25})

        probabilities = adapter.predict_proba(result.artifact_uri, [[5.0, 1.0], [-5.0, 2.0]])

        assert probabilities is not None
        assert len(probabilities) == 2
        assert all(len(row) == 2 for row in probabilities)
        assert all(sum(row) == pytest.approx(1.0) for row in probabilities)
