"""Pure dataclasses for one backtest: its planned steps and per-step outcomes.

Framework-light and database-free, mirroring `app/evaluation/base.py`'s own
posture — nothing here touches SQLAlchemy or knows what a `BacktestRun`/
`Prediction` ORM row is. The service layer (`app/services/backtest.py`) is
the one place a database session exists, and maps rows onto
`GradedPredictionRow` before calling `app.backtest.engine.aggregate`.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class BacktestStepPlan:
    """The `as_of` timestamps to walk, after capping, and whether capping shortened it.

    `as_of_values` is already the *final*, capped list — every value in it
    is walked; `requested_steps` is what the *uncapped* request would have
    needed, kept so the response can honestly report "requested N, ran M".
    """

    as_of_values: list[datetime]
    effective_end: datetime
    truncated: bool
    requested_steps: int


@dataclass(frozen=True, slots=True)
class GradedPredictionRow:
    """One backtest prediction's outcome, shaped for aggregation.

    Mapped from a real `Prediction` ORM row by the service layer — never
    queried directly here. `classes`/`probabilities` are `None` together
    whenever the model adapter produced neither (every regressor today),
    the same pairing `Prediction`'s own model already enforces.
    """

    predicted_value: Any
    actual_outcome: Any
    classes: list[Any] | None
    probabilities: dict[str, float] | None
