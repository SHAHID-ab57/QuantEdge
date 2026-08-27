"""Tests for `LogisticRegressionAdapter` — a real scikit-learn baseline classifier."""

from pathlib import Path

import pytest

import app.training.adapters.logistic_regression as logistic_regression_module
from app.training.adapters.logistic_regression import LogisticRegressionAdapter
from app.training.base import SplitMatrix, TrainingDataset
from app.training.errors import TrainingExecutionError
from app.training.serialization import LocalDiskModelSerializer


def make_dataset() -> TrainingDataset:
    # Deterministic, perfectly separable-by-sign data: label is "pos" when the
    # single feature is positive, "neg" otherwise — a baseline classifier should
    # learn this trivially, so metrics are exact and reproducible.
    train_x = [[float(i)] for i in range(-10, 10)]
    train_y = ["pos" if x[0] > 0 else "neg" for x in train_x]
    validation_x = [[5.0], [-5.0], [3.0], [-3.0]]
    validation_y = ["pos", "neg", "pos", "neg"]
    test_x = [[1.0], [-1.0]]
    test_y = ["pos", "neg"]
    return TrainingDataset(
        dataset_version="ds-test",
        feature_columns=("x",),
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
        logistic_regression_module, "default_serializer", LocalDiskModelSerializer(tmp_path)
    )


class TestInitialize:
    def test_accepts_valid_hyperparameters(self) -> None:
        LogisticRegressionAdapter().initialize({"max_iter": 100, "C": 0.5, "random_seed": 1})

    def test_uses_defaults_when_omitted(self) -> None:
        LogisticRegressionAdapter().initialize({})


class TestTrain:
    def test_raises_when_no_real_data_is_loaded(self) -> None:
        adapter = LogisticRegressionAdapter()
        with pytest.raises(TrainingExecutionError):
            adapter.train(TrainingDataset(dataset_version="ds-1"), {})

    def test_wraps_a_scikit_learn_fit_failure_as_a_training_execution_error(self) -> None:
        adapter = LogisticRegressionAdapter()
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
        adapter = LogisticRegressionAdapter()

        result = adapter.train(make_dataset(), {"max_iter": 200})

        assert result.metrics["accuracy"] == pytest.approx(1.0)
        assert result.metrics["f1"] == pytest.approx(1.0)
        assert result.artifact_uri.startswith("file://")
        assert set(result.summary["classes"]) == {"neg", "pos"}
        assert result.summary["target_column"] == "label"
        assert result.summary["feature_columns"] == ["x"]
        assert result.summary["n_train"] == 20
        assert result.summary["n_validation"] == 4
        assert result.summary["n_test"] == 2
        assert "confusion_matrix" in result.summary
        assert "test_metrics" in result.summary
        assert result.summary["test_metrics"]["accuracy"] == pytest.approx(1.0)

    def test_hyperparameters_are_recorded_in_the_summary(self) -> None:
        adapter = LogisticRegressionAdapter()

        result = adapter.train(make_dataset(), {"max_iter": 50, "C": 2.0, "random_seed": 7})

        assert result.summary["hyperparameters"] == {"max_iter": 50, "C": 2.0, "random_seed": 7}


class TestPredict:
    def test_loads_the_saved_model_and_predicts(self) -> None:
        adapter = LogisticRegressionAdapter()
        result = adapter.train(make_dataset(), {})

        predictions = adapter.predict(result.artifact_uri, [[5.0], [-5.0]])

        assert predictions == ["pos", "neg"]
