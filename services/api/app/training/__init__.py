"""Machine Learning Training Framework (BC4 — AI Research & Training).

Reusable, framework-agnostic training *orchestration*: a job lifecycle, a
fixed pipeline of stages, and a Strategy + Registry extension point for a
model adapter — the same shape `app/features/`, `app/ml_datasets/`, and
`app/dataset_validation/` already use for their own pluggable pieces. See
`ARCHITECTURE.md` § "Machine Learning Training Framework" for the full design.

This package implements **no real model training**. `app/training/adapters/
placeholder.py` is the only registered adapter today; a future TensorFlow,
PyTorch, or scikit-learn integration registers a new `ModelAdapter`
subclass here and needs no change to the pipeline, service, repository, or
API — the same extension guarantee every other registry in this codebase
already makes.
"""
