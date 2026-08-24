"""Domain errors for the indicator engine.

Every error extends ``AppError``, so the application's existing exception
handler turns each into the same ``{"code", "detail"}`` JSON envelope the
rest of the API already uses — no indicator-specific error handling exists
in the HTTP layer.
"""

from fastapi import status

from app.core.exceptions import AppError


class IndicatorNotFoundError(AppError):
    """Raised when the requested indicator is not in the registry."""

    def __init__(self, name: str, available: tuple[str, ...] = ()) -> None:
        suffix = f"; available: {', '.join(available)}" if available else ""
        super().__init__(
            f"Indicator {name!r} is not registered{suffix}",
            code="indicator_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
        self.name = name


class InvalidIndicatorParameterError(AppError):
    """Raised when a supplied parameter is missing, unknown, or out of range."""

    def __init__(self, parameter: str, reason: str) -> None:
        super().__init__(
            f"Parameter {parameter!r} {reason}",
            code="invalid_indicator_parameter",
        )
        self.parameter = parameter


class InsufficientDataError(AppError):
    """Raised when fewer candles are available than the indicator needs.

    Deliberately an error rather than an all-``null`` result: a chart of
    nothing looks the same whether the market is quiet or the range was too
    short, and a researcher needs to be able to tell those apart.
    """

    def __init__(self, indicator: str, required: int, available: int) -> None:
        super().__init__(
            f"Indicator {indicator!r} needs at least {required} candles "
            f"for these parameters; only {available} are available in this range",
            code="insufficient_data",
        )
        self.required = required
        self.available = available


class IndicatorExecutionError(AppError):
    """Raised when an indicator's own calculation raises unexpectedly.

    Wrapping the original exception keeps one indicator's bug from
    surfacing as an opaque 500 for the whole API, and names the culprit so
    it is obvious which implementation to look at.
    """

    def __init__(self, indicator: str, reason: str) -> None:
        super().__init__(
            f"Indicator {indicator!r} failed during calculation: {reason}",
            code="indicator_execution_failed",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        self.indicator = indicator


class DuplicateIndicatorError(RuntimeError):
    """Raised at import time when two indicators claim the same registry name.

    Not an ``AppError``: this is a programming mistake that must fail fast
    at startup, never a condition an HTTP client can trigger or recover
    from.
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"An indicator named {name!r} is already registered; "
            "indicator names must be unique across the registry"
        )
        self.name = name
