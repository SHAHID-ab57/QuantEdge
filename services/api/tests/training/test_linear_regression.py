"""Tests for `LinearRegressionAdapter` — a real scikit-learn baseline regressor."""

from pathlib import Path

import pytest

import app.training.adapters.linear_regression as linear_regression_module
from app.training.adapters.linear_regression import LinearRegressionAdapter
from app.training.base import SplitMatrix, TrainingDataset
from app.training.errors import TrainingExecutionError
from app.training.serialization import LocalDiskModelSerializer


def make_dataset() -> TrainingDataset:
    # y = 2x exactly — a linear baseline should fit this with ~zero error,
    # so metrics are deterministic and easy to assert on.
    train_x = [[float(i)] for i in range(20)]
    train_y = [2.0 * x[0] for x in train_x]
    validation_x = [[20.0], [21.0], [22.0]]
    validation_y = [40.0, 42.0, 44.0]
    test_x = [[30.0], [31.0]]
    test_y = [60.0, 62.0]
    return TrainingDataset(
        dataset_version="ds-test",
        feature_columns=("x",),
        target_column="y",
        train=SplitMatrix(X=train_x, y=train_y),
        validation=SplitMatrix(X=validation_x, y=validation_y),
        test=SplitMatrix(X=test_x, y=test_y),
    )


@pytest.fixture(autouse=True)
def _local_serializer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        linear_regression_module, "default_serializer", LocalDiskModelSerializer(tmp_path)
    )


class TestInitialize:
    def test_accepts_valid_hyperparameters(self) -> None:
        LinearRegressionAdapter().initialize({"fit_intercept": False})

    def test_uses_defaults_when_omitted(self) -> None:
        LinearRegressionAdapter().initialize({})


class TestTrain:
    def test_raises_when_no_real_data_is_loaded(self) -> None:
        adapter = LinearRegressionAdapter()
        with pytest.raises(TrainingExecutionError):
            adapter.train(TrainingDataset(dataset_version="ds-1"), {})

    def test_wraps_a_scikit_learn_fit_failure_as_a_training_execution_error(self) -> None:
        adapter = LinearRegressionAdapter()
        broken = TrainingDataset(
            dataset_version="ds-1",
            feature_columns=("x",),
            target_column="y",
            # Mismatched X/y row counts — scikit-learn raises ValueError on `.fit`.
            train=SplitMatrix(X=[[1.0], [2.0]], y=[1.0]),
            validation=SplitMatrix(X=[[1.0]], y=[1.0]),
        )

        with pytest.raises(TrainingExecutionError):
            adapter.train(broken, {})

    def test_trains_and_reports_near_zero_error_on_a_linear_relationship(self) -> None:
        adapter = LinearRegressionAdapter()

        result = adapter.train(make_dataset(), {})

        assert result.metrics["mae"] == pytest.approx(0.0, abs=1e-8)
        assert result.metrics["rmse"] == pytest.approx(0.0, abs=1e-8)
        assert result.metrics["r2"] == pytest.approx(1.0)
        assert result.artifact_uri.startswith("file://")
        assert result.summary["coefficients"] == pytest.approx([2.0])
        assert result.summary["intercept"] == pytest.approx(0.0, abs=1e-8)
        assert result.summary["n_train"] == 20
        assert result.summary["n_validation"] == 3
        assert result.summary["n_test"] == 2
        assert result.summary["test_metrics"]["r2"] == pytest.approx(1.0)

    def test_fit_intercept_hyperparameter_is_recorded(self) -> None:
        adapter = LinearRegressionAdapter()

        result = adapter.train(make_dataset(), {"fit_intercept": False})

        assert result.summary["hyperparameters"] == {"fit_intercept": False}


class TestPredict:
    def test_loads_the_saved_model_and_predicts(self) -> None:
        adapter = LinearRegressionAdapter()
        result = adapter.train(make_dataset(), {})

        predictions = adapter.predict(result.artifact_uri, [[5.0], [10.0]])

        assert predictions == pytest.approx([10.0, 20.0])
