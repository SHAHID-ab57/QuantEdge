"""Model Evaluation & Benchmarking Engine.

The sixth Strategy + Registry on this platform (after features, indicators,
targets, validation rules, and model adapters): a **Metric** is the
extension point, resolved by name through `MetricRegistry`. `EvaluationEngine`
runs every metric applicable to a given `model_kind` ("classification" or
"regression") over one model's predictions; `benchmark.compare` compares
several already-completed `TrainingJob`s (different models, the same
dataset/target) using the metrics each one already recorded.

Nothing here duplicates the Training Framework, the model adapter registry,
or Experiment Management — `LogisticRegressionAdapter`/`LinearRegressionAdapter`
call `EvaluationEngine.evaluate` for the exact numbers they used to compute
inline, and `_make_update_experiment_hook` (unchanged) is still the only place
a metric gets written onto an `Experiment`. This package only adds a
consistent, pluggable *place* those numbers come from, and a read-only
comparison over what's already stored.
"""
