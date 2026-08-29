"""Builtin metric loader — mirrors `app/training/adapters/__init__.py`'s own
`load_builtin_model_adapters` exactly: importing a metric module runs its
`@register` decorators, so this function only needs to import each module
once, idempotently, no matter how many times it's called."""

_loaded = False


def load_builtin_metrics() -> None:
    """Import every builtin metric module, registering each with `@register`.

    Safe to call repeatedly (e.g. once per request during tests) — imports
    after the first are no-ops, and `MetricRegistry.register` itself would
    raise `DuplicateMetricError` if a module were somehow imported twice.
    """
    global _loaded
    if _loaded:
        return
    from app.evaluation.metrics import classification, regression  # noqa: F401

    _loaded = True
