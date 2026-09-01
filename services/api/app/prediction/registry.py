"""The Live Prediction Service's one reused registry.

`app/evaluation/registry.py` exists because the Evaluation Engine has a
real, new extension point (a pluggable `Metric`). Prediction has no
equivalent for *reconstructing a feature vector* — that's always "drive the
Feature Engineering Engine with the experiment's own recorded `feature_set`"
(one way, not several to choose between; `FeatureService.build_raw` already
owns it). Running the model, though, genuinely does resolve through an
existing pluggable registry — the Training Framework's own model adapter
registry, resolving a job's `model_type` (today: `logistic_regression`,
`linear_regression`, `placeholder`; a future TensorFlow/PyTorch adapter
needs no change here or anywhere in this package).

This module is the one place `app/services/prediction.py` reaches for that
registry, mirroring `EvaluationService`'s own `model_adapter_registry`
dependency exactly — a second registry would just shadow one that already
exists, but importing `app.training.registry` through this module's own
name gives a future prediction-specific override exactly one seam to
change, without touching the service itself.
"""

from app.training.registry import ModelAdapterRegistry
from app.training.registry import default_registry as _default_model_adapter_registry


def get_model_adapter_registry() -> ModelAdapterRegistry:
    """The Training Framework's own adapter registry — resolves a job's
    `model_type` to its `model_kind` (classification/regression/placeholder),
    the same way `EvaluationService.benchmark` already does for a benchmark
    candidate's own `model_kind`."""
    return _default_model_adapter_registry
