"""Domain errors for the ML Dataset Builder.

Every request-time error extends ``AppError``, matching the features,
indicators, and dataset-validation engines exactly — the application's
existing exception handler turns each into the same ``{"code", "detail"}``
JSON envelope with no ML-specific error handling in the HTTP layer.
Startup-time errors (a duplicate target name) are plain ``RuntimeError``
subclasses instead, since no HTTP request can trigger them.
"""

from fastapi import status

from app.core.exceptions import AppError


class TargetNotFoundError(AppError):
    """Raised when the requested target generator is not in the registry."""

    def __init__(self, name: str, available: tuple[str, ...] = ()) -> None:
        suffix = f"; available: {', '.join(available)}" if available else ""
        super().__init__(
            f"Target {name!r} is not registered{suffix}",
            code="target_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
        self.name = name


class InvalidTargetParameterError(AppError):
    """Raised when a supplied target parameter is missing, unknown, or out of range."""

    def __init__(self, target: str, reason: str) -> None:
        super().__init__(
            f"Target {target!r}: {reason}",
            code="invalid_target_parameter",
        )
        self.target = target


class InsufficientTargetDataError(AppError):
    """Raised when fewer candles are available than a target's horizon needs.

    Shares the ``insufficient_data`` code with the feature and indicator
    engines' equivalents, since it is the same situation from the caller's
    point of view (not enough data for what was asked), just at the
    opposite end of the series: a target needs at least ``horizon + 1``
    candles (one to predict *from*, plus the horizon to look past it),
    where a feature needs at least its warmup.
    """

    def __init__(self, target: str, horizon: int, available: int) -> None:
        super().__init__(
            f"Target {target!r} needs at least {horizon + 1} candles for horizon={horizon}; "
            f"only {available} are available in this range",
            code="insufficient_data",
        )
        self.target = target
        self.horizon = horizon
        self.available = available


class TargetExecutionError(AppError):
    """Raised when a target generator's own computation raises unexpectedly."""

    def __init__(self, target: str, reason: str) -> None:
        super().__init__(
            f"Target {target!r} failed during generation: {reason}",
            code="target_execution_failed",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        self.target = target


class TargetAlignmentError(AppError):
    """Raised when a generator's output violates the forward-looking contract.

    Either the returned column isn't the same length as the candles it was
    given, or a value inside the declared horizon window is unexpectedly
    defined, or a value outside it is unexpectedly ``None``. Any of these
    means the generator's own bookkeeping about what it can and cannot know
    is wrong — exactly the class of bug this contract exists to catch
    before a mislabeled dataset ever reaches a training job.
    """

    def __init__(self, target: str, reason: str) -> None:
        super().__init__(
            f"Target {target!r} violated its forward-looking contract: {reason}",
            code="target_alignment_error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        self.target = target


class DuplicateTargetColumnError(AppError):
    """Raised when two requested targets (or a target and a feature) would collide.

    A silently-overwritten column is the worst possible outcome for a
    training dataset, whether the collision is between two targets or
    between a target and a feature — the latter is arguably worse, since it
    could silently replace an input feature with a label or vice versa.
    """

    def __init__(self, column: str, first: str, second: str) -> None:
        super().__init__(
            f"Column {column!r} would be produced by both {first!r} and {second!r}; "
            "request them with different parameters or drop one",
            code="duplicate_target_column",
        )
        self.column = column


class InvalidSplitRatiosError(AppError):
    """Raised when the requested train/validation/test ratios don't form a valid split."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Invalid split ratios: {reason}",
            code="invalid_split_ratios",
        )


class EmptyMLDatasetError(AppError):
    """Raised when every row was dropped, leaving nothing to train on.

    Distinct from "no candles stored": the range did have data, but every
    row was consumed by warmup trimming, target-horizon trimming, or both.
    """

    def __init__(self, candles: int, warmup: int, horizon: int) -> None:
        super().__init__(
            f"Every row was dropped: {candles} candles were loaded but the requested "
            f"features need {warmup} candles of warmup and the requested targets need "
            f"{horizon} candles of horizon at the end. Widen the date range, reduce the "
            "largest feature period, or reduce the largest target horizon",
            code="empty_ml_dataset",
        )
        self.candles = candles
        self.warmup = warmup
        self.horizon = horizon


class DuplicateTargetError(RuntimeError):
    """Raised at import time when two target generators claim the same registry name.

    Not an ``AppError``: this is a programming mistake that must fail fast
    at startup, never a condition an HTTP client can trigger or recover
    from — the same split `DuplicateFeatureError`/`DuplicateIndicatorError`
    already establish.
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"A target named {name!r} is already registered; "
            "target names must be unique across the registry"
        )
        self.name = name
