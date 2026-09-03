"""Domain errors for the Backtesting Engine.

Every failure that can also happen to a single live prediction (an unknown
training job, a job that hasn't completed, a job never trained on real
data, an unknown market, too little candle history) already has a named
error raised by `PredictionService.run`/`grade_now` themselves, reused
verbatim by the backtest walker — never duplicated here. Only what's
genuinely new to walking a *range* is defined below.
"""

from datetime import datetime

from fastapi import status

from app.core.exceptions import AppError


class BacktestRunNotFoundError(AppError):
    """Raised when the requested Backtest History run id does not exist."""

    def __init__(self, run_id: object) -> None:
        super().__init__(
            f"Backtest run {run_id} not found",
            code="backtest_run_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidBacktestRangeError(AppError):
    """Raised when the requested date range is empty or backwards."""

    def __init__(self, start: datetime, end: datetime) -> None:
        super().__init__(
            f"Invalid backtest range: end ({end.isoformat()}) must be after "
            f"start ({start.isoformat()})",
            code="invalid_backtest_range",
        )


class InvalidBacktestStepError(AppError):
    """Raised when the requested step is finer than the job's own timeframe.

    Walking at a resolution finer than the model's own candle timeframe
    would just re-predict the identical row multiple times — never useful,
    always a sign the request meant something else.
    """

    def __init__(self, step: str, timeframe: str) -> None:
        super().__init__(
            f"Backtest step {step!r} is finer than training job's own timeframe "
            f"{timeframe!r} — the step must be the same as, or coarser than, the "
            "timeframe the model was trained at",
            code="invalid_backtest_step",
        )


class InvalidBacktestSortError(AppError):
    """Raised when a Backtest History list request names an unsupported sort column."""

    def __init__(self, sort: str, direction: str, available: tuple[str, ...]) -> None:
        super().__init__(
            f"Invalid sort {sort!r}/{direction!r}. Available sort columns: "
            f"{', '.join(available)}; direction must be 'asc' or 'desc'",
            code="invalid_backtest_sort",
        )


class BacktestRangeExceedsAvailableDataError(AppError):
    """Raised when the requested range reaches past the last real candle
    actually stored for this symbol/timeframe.

    Rejected outright, not silently truncated: `PredictionService.run` —
    reused completely unmodified — never interpolates, so any step whose
    `as_of` lands past the latest real candle resolves to that *same* last
    candle instead of a genuinely new one. Left unchecked, that collapses
    every such step into repeated, identical predictions, folded into
    `aggregate_metrics` right alongside the genuinely distinct ones — a
    misleading number that looks like an ordinary completed backtest,
    exactly the failure mode this milestone exists to catch rather than
    produce. This is a distinct concern from `InvalidBacktestRangeError`
    (an empty/backwards range) and from step-count capping (a range that's
    merely too *long*, honestly shortened and reported, never rejected) —
    a range can be perfectly well-formed and well within `MAX_BACKTEST_STEPS`
    and still reach past what's actually been ingested.
    """

    def __init__(
        self,
        requested_end: datetime,
        latest_candle_open_time: datetime,
        available_through: datetime,
    ) -> None:
        super().__init__(
            f"Requested backtest end ({requested_end.isoformat()}) is past the latest "
            f"stored candle for this symbol/timeframe (open_time="
            f"{latest_candle_open_time.isoformat()}, covering data through "
            f"{available_through.isoformat()}) — shrink `end` to "
            f"{available_through.isoformat()} or earlier, or wait for more candles to "
            "be ingested",
            code="backtest_range_exceeds_available_data",
        )
