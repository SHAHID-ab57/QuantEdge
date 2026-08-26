"""The placeholder model adapter — the only one registered today.

Performs **no real training**. It exists so the pipeline, lifecycle, API,
and frontend can be built, exercised, and tested end to end before a real
TensorFlow/PyTorch/scikit-learn adapter is wired in — the framework's
stated purpose ("orchestration, lifecycle management, and extensibility",
not "produce a usable model").

Every fabricated number is a **deterministic** function of the job's own
`hyperparameters` (never of wall-clock time or randomness), so a test can
assert an exact metric value and a re-run of the same job with the same
hyperparameters reproduces the same fabricated result — the one property
worth preserving even in a placeholder, since it is the same reproducibility
discipline `app/features/`/`app/ml_datasets/` already hold themselves to.
"""

from collections.abc import Mapping
from typing import Any

from app.training.base import ModelAdapter, ModelAdapterMetadata, TrainingDataset, TrainingResult
from app.training.registry import register


@register
class PlaceholderModelAdapter(ModelAdapter):
    """A deterministic stand-in for a real TensorFlow/PyTorch/scikit-learn model."""

    metadata = ModelAdapterMetadata(
        name="placeholder",
        label="Placeholder Model",
        description=(
            "Fabricates deterministic metrics to exercise the training pipeline. "
            "Not a real model — no framework runs behind it."
        ),
        framework="placeholder",
        hyperparameter_hints=("epochs", "learning_rate"),
    )

    def initialize(self, hyperparameters: Mapping[str, Any]) -> None:
        """No model to build — validates only that hyperparameters are plain JSON-shaped."""
        for key, value in hyperparameters.items():
            if not isinstance(key, str):
                raise TypeError(f"hyperparameter keys must be strings, got {type(key).__name__}")
            if isinstance(value, (dict, list)):
                raise TypeError(
                    f"hyperparameter {key!r} must be a scalar (str/int/float/bool), "
                    f"got {type(value).__name__}"
                )

    def train(self, dataset: TrainingDataset, hyperparameters: Mapping[str, Any]) -> TrainingResult:
        epochs = max(1, int(hyperparameters.get("epochs", 1)))
        learning_rate = float(hyperparameters.get("learning_rate", 0.01))

        # A monotonically decreasing fabricated loss curve — deterministic in
        # `epochs`/`learning_rate` only, never in wall-clock time or randomness.
        final_loss = round(1.0 / (1.0 + epochs * max(learning_rate, 1e-6) * 10), 6)
        final_accuracy = round(1.0 - final_loss, 6)

        return TrainingResult(
            metrics={
                "placeholder_loss": final_loss,
                "placeholder_accuracy": final_accuracy,
            },
            artifact_uri=f"placeholder://training-runs/{dataset.dataset_version}",
            summary={
                "epochs": epochs,
                "learning_rate": learning_rate,
                "dataset_version": dataset.dataset_version,
                "note": "Fabricated by PlaceholderModelAdapter; not a real training run.",
            },
        )
