"""Domain errors for the feature engineering engine.

Every error extends ``AppError``, so the application's existing exception
handler turns each into the same ``{"code", "detail"}`` JSON envelope the
rest of the API already uses — no feature-specific error handling exists in
the HTTP layer, exactly as with indicators.
"""

from fastapi import status

from app.core.exceptions import AppError


class FeatureNotFoundError(AppError):
    """Raised when the requested feature generator is not in the registry."""

    def __init__(self, name: str, available: tuple[str, ...] = ()) -> None:
        suffix = f"; available: {', '.join(available)}" if available else ""
        super().__init__(
            f"Feature {name!r} is not registered{suffix}",
            code="feature_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
        self.name = name


class InvalidFeatureParameterError(AppError):
    """Raised when a supplied feature parameter is missing, unknown, or out of range."""

    def __init__(self, feature: str, reason: str) -> None:
        super().__init__(
            f"Feature {feature!r}: {reason}",
            code="invalid_feature_parameter",
        )
        self.feature = feature


class InsufficientFeatureDataError(AppError):
    """Raised when fewer candles are available than a generator needs.

    Shares the ``insufficient_data`` code with the indicator engine's
    equivalent so a client handles one code rather than two for the same
    situation, while wording the message for the feature context. Checked
    by the pipeline *before* generation so it surfaces as an actionable
    400 rather than being wrapped as an opaque 500 by the generic
    generator-failure boundary.
    """

    def __init__(self, feature: str, required: int, available: int) -> None:
        super().__init__(
            f"Feature {feature!r} needs at least {required} candles "
            f"for these parameters; only {available} are available in this range",
            code="insufficient_data",
        )
        self.feature = feature
        self.required = required
        self.available = available


class FeatureExecutionError(AppError):
    """Raised when a generator's own computation raises unexpectedly.

    Wrapping the original exception keeps one generator's bug from
    surfacing as an opaque 500 for the whole dataset request, and names the
    culprit so it is obvious which implementation to look at.
    """

    def __init__(self, feature: str, reason: str) -> None:
        super().__init__(
            f"Feature {feature!r} failed during generation: {reason}",
            code="feature_execution_failed",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        self.feature = feature


class DuplicateFeatureColumnError(AppError):
    """Raised when two requested features would produce the same column name.

    A silently-overwritten column is the worst possible outcome for a
    training dataset: the model trains on data the researcher did not
    intend and has no way to notice. Failing loudly with both culprits
    named is the only safe behaviour.
    """

    def __init__(self, column: str, first: str, second: str) -> None:
        super().__init__(
            f"Column {column!r} would be produced by both {first!r} and {second!r}; "
            "request them with different parameters or drop one",
            code="duplicate_feature_column",
        )
        self.column = column


class EmptyDatasetError(AppError):
    """Raised when every row was dropped, leaving nothing to train on.

    Distinct from "no candles stored": the range *did* have data, but every
    row contained a warmup ``null`` — usually a period longer than the
    requested range. Reporting that specifically is what lets a researcher
    fix it (shorten the period, or widen the range) instead of guessing.
    """

    def __init__(self, candles: int, warmup: int) -> None:
        super().__init__(
            f"Every row was dropped: {candles} candles were loaded but the requested "
            f"features need {warmup} candles of warmup. Widen the date range or "
            "reduce the largest period parameter",
            code="empty_dataset",
        )
        self.candles = candles
        self.warmup = warmup


class MissingFeatureDependencyError(AppError):
    """Raised when a requested feature's declared dependencies aren't also requested.

    A feature's ``metadata.dependencies`` (see ``FeatureMetadata``) names
    other registered features it needs alongside it. No shipped generator
    declares one today — this is the request-time half of an extension
    point — but the check is real: a future feature that depends on
    another must be requested together with it, and building a dataset
    that silently omits a stated dependency is exactly the kind of
    "looks fine, is wrong" defect this whole context exists to prevent.
    """

    def __init__(self, feature: str, missing: tuple[str, ...]) -> None:
        names = ", ".join(repr(name) for name in missing)
        super().__init__(
            f"Feature {feature!r} depends on {names}, which "
            f"{'was' if len(missing) == 1 else 'were'} not included in this request. "
            "Add it to `features` alongside this one.",
            code="missing_feature_dependency",
        )
        self.feature = feature
        self.missing = missing


class UnknownFeatureDependencyError(RuntimeError):
    """Raised at startup when a generator declares a dependency that isn't registered.

    Not an ``AppError``: like ``DuplicateFeatureError``, this is a
    programming mistake in a generator's own declaration, caught once when
    the registry is validated at startup, never a condition an HTTP client
    can trigger.
    """

    def __init__(self, feature: str, unknown: tuple[str, ...]) -> None:
        names = ", ".join(repr(name) for name in unknown)
        super().__init__(
            f"Feature {feature!r} declares a dependency on {names}, which "
            f"{'is' if len(unknown) == 1 else 'are'} not a registered feature"
        )
        self.feature = feature
        self.unknown = unknown


class FeatureDependencyCycleError(RuntimeError):
    """Raised at startup when the registry's dependency graph contains a cycle.

    Not an ``AppError``, for the same reason as ``UnknownFeatureDependencyError``:
    a cycle can only be created by how generators declare their own
    dependencies, so it is a startup-time integrity check, not something a
    request can provoke.
    """

    def __init__(self, cycle: tuple[str, ...]) -> None:
        path = " → ".join(cycle)
        super().__init__(f"Feature dependency cycle detected: {path}")
        self.cycle = cycle


class DuplicateFeatureError(RuntimeError):
    """Raised at import time when two generators claim the same registry name.

    Not an ``AppError``: this is a programming mistake that must fail fast
    at startup, never a condition an HTTP client can trigger or recover
    from.
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"A feature named {name!r} is already registered; "
            "feature names must be unique across the registry"
        )
        self.name = name
