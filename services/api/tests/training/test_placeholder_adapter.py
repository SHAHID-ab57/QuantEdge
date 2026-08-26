"""Tests for `PlaceholderModelAdapter` — determinism is the one property it must hold."""

import pytest

from app.training.adapters.placeholder import PlaceholderModelAdapter
from app.training.base import TrainingDataset


class TestInitialize:
    def test_accepts_scalar_hyperparameters(self) -> None:
        PlaceholderModelAdapter().initialize({"epochs": 5, "learning_rate": 0.01})

    def test_rejects_a_nested_hyperparameter_value(self) -> None:
        with pytest.raises(TypeError):
            PlaceholderModelAdapter().initialize({"epochs": {"nested": 1}})

    def test_rejects_a_non_string_hyperparameter_key(self) -> None:
        with pytest.raises(TypeError):
            PlaceholderModelAdapter().initialize({1: "epochs"})  # type: ignore[dict-item]


class TestTrain:
    def test_is_deterministic_for_the_same_inputs(self) -> None:
        adapter = PlaceholderModelAdapter()
        dataset = TrainingDataset(dataset_version="ds-123")
        params = {"epochs": 5, "learning_rate": 0.01}

        first = adapter.train(dataset, params)
        second = adapter.train(dataset, params)

        assert first.metrics == second.metrics
        assert first.artifact_uri == second.artifact_uri
        assert first.summary == second.summary

    def test_differs_for_different_hyperparameters(self) -> None:
        adapter = PlaceholderModelAdapter()
        dataset = TrainingDataset(dataset_version="ds-123")

        low_epochs = adapter.train(dataset, {"epochs": 1})
        high_epochs = adapter.train(dataset, {"epochs": 50})

        assert low_epochs.metrics["placeholder_loss"] != high_epochs.metrics["placeholder_loss"]

    def test_more_epochs_yields_lower_fabricated_loss(self) -> None:
        adapter = PlaceholderModelAdapter()
        dataset = TrainingDataset(dataset_version="ds-123")

        result_1 = adapter.train(dataset, {"epochs": 1})
        result_10 = adapter.train(dataset, {"epochs": 10})

        assert result_10.metrics["placeholder_loss"] < result_1.metrics["placeholder_loss"]

    def test_defaults_epochs_and_learning_rate_when_omitted(self) -> None:
        adapter = PlaceholderModelAdapter()
        dataset = TrainingDataset(dataset_version="ds-123")

        result = adapter.train(dataset, {})

        assert result.summary["epochs"] == 1
        assert result.summary["learning_rate"] == 0.01

    def test_artifact_uri_carries_the_dataset_version(self) -> None:
        adapter = PlaceholderModelAdapter()
        result = adapter.train(TrainingDataset(dataset_version="ds-xyz"), {})
        assert result.artifact_uri == "placeholder://training-runs/ds-xyz"

    def test_metrics_and_accuracy_sum_to_one(self) -> None:
        adapter = PlaceholderModelAdapter()
        result = adapter.train(TrainingDataset(dataset_version="ds-123"), {"epochs": 3})
        loss = result.metrics["placeholder_loss"]
        accuracy = result.metrics["placeholder_accuracy"]
        assert round(loss + accuracy, 6) == 1.0
