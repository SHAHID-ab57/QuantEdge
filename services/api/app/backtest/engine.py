"""The Backtest Engine: plans a range of `as_of` steps, and aggregates
their graded outcomes — the two pure computations a backtest needs beyond
the live prediction and grading code it otherwise calls unmodified.

Framework-light, mirroring `app/evaluation/benchmark.py`'s own posture:
this module does not touch the database, does not call
`PredictionService`, and does not know what a `BacktestRun`/`Prediction`
ORM row is — `app/services/backtest.py` is the one place all of that
happens, mapping rows onto the plain dataclasses this module accepts.

Aggregation reuses `app.evaluation.engine.default_engine` — the *exact*
`EvaluationEngine` instance every other metric consumer on this platform
already reads from — never a second copy of `accuracy`/`mae`/etc.
"""

import math
from collections.abc import Sequence
from datetime import datetime, timedelta

from app.backtest.base import BacktestStepPlan, GradedPredictionRow
from app.backtest.errors import InvalidBacktestRangeError
from app.evaluation.base import EvaluationReport
from app.evaluation.engine import default_engine


def plan_steps(
    *, start: datetime, end: datetime, step_interval: timedelta, max_steps: int
) -> BacktestStepPlan:
    """Compute every `as_of` to walk between `[start, end)`, capped at `max_steps`.

    Half-open, matching every other candle-range convention on this
    platform (`app.services.market_query.normalize_range`,
    `FeatureService.build_raw`'s own `end`): `as_of` values are
    `start, start + step_interval, ...`, stopping *before* `end`.

    Capped from the end, keeping the *earliest* steps — the same direction
    `apps/dashboard/src/features/replay/hooks/use-replay-candles.ts`'s own
    `MAX_REPLAY_CANDLES` already truncates a session's candles from,
    reusing the same "keep the front, cut the back, report it honestly"
    convention rather than inventing a different one for this platform's
    other range-capping feature.
    """
    if end <= start:
        raise InvalidBacktestRangeError(start, end)

    total_seconds = (end - start).total_seconds()
    step_seconds = step_interval.total_seconds()
    requested_steps = math.ceil(total_seconds / step_seconds)
    truncated = requested_steps > max_steps
    actual_steps = min(requested_steps, max_steps)

    as_of_values = [start + step_interval * i for i in range(actual_steps)]
    effective_end = as_of_values[-1] + step_interval if as_of_values else start

    return BacktestStepPlan(
        as_of_values=as_of_values,
        effective_end=effective_end,
        truncated=truncated,
        requested_steps=requested_steps,
    )


def aggregate(model_kind: str, rows: Sequence[GradedPredictionRow]) -> EvaluationReport:
    """Aggregate every graded prediction from one backtest into one report.

    `y_true`/`y_pred` are read straight off `rows` — every row here is
    already known-graded (the service layer only includes rows whose
    `actual_outcome` is not `None`); `y_proba` is reconstructed, ordered by
    each row's own `classes`, only when *every* row carries both
    `classes`/`probabilities` (every regressor, and any classifier without
    `predict_proba`, has neither) — `EvaluationEngine.evaluate` already
    degrades gracefully (a skipped `roc_auc`, not an error) when given
    `None`, so this never fabricates a probability row to avoid that.
    """
    y_true = [row.actual_outcome for row in rows]
    y_pred = [row.predicted_value for row in rows]

    y_proba: list[list[float]] | None = None
    if rows and all(row.classes is not None and row.probabilities is not None for row in rows):
        y_proba = []
        for row in rows:
            # Narrowed by the `all(...)` check above; re-asserted per-row
            # (rather than a `cast`/`# type: ignore`) since a static type
            # checker cannot see through that generator expression.
            assert row.classes is not None
            assert row.probabilities is not None
            y_proba.append([row.probabilities[str(label)] for label in row.classes])

    return default_engine.evaluate(model_kind, y_true, y_pred, y_proba)
