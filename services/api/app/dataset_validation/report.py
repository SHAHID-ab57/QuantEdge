"""The validation report — the structured output the whole engine exists to produce.

Every field here is a plain, JSON-serializable dataclass; ``app/schemas/
dataset_validation.py`` is the one place these are mapped onto the wire —
the same Pydantic-free-engine / DTOs-at-the-edge split ``app/features/``
and ``app/indicators/`` already follow.
"""

from dataclasses import dataclass
from datetime import datetime

from app.dataset_validation.base import ValidationIssue


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    """Headline counts across every issue found, regardless of category."""

    total_checks: int
    errors: int
    warnings: int
    info: int


@dataclass(frozen=True, slots=True)
class CategorySummary:
    """Issue counts scoped to one validation category."""

    errors: int
    warnings: int
    info: int


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The outcome of running the validation engine over one dataset.

    ``passed`` is the quality gate's verdict: ``True`` only when zero
    ``error``-severity issues were found. A ``warning`` or ``info`` issue is
    always reported but never flips this to ``False`` — the same "some
    findings block, some just inform" posture a linter's exit code takes.
    """

    dataset_id: str
    symbol: str
    timeframe: str
    engine_version: str
    validated_at: datetime
    passed: bool
    #: Rule names actually run, in the order they ran — either every
    #: registered rule, or the caller-chosen subset.
    rules_run: tuple[str, ...]
    summary: ValidationSummary
    categories: dict[str, CategorySummary]
    issues: tuple[ValidationIssue, ...]
    #: Rows/columns in the *validated* dataset, for a report reader who
    #: hasn't also fetched the dataset itself.
    rows: int
    columns: int
    duration_ms: float
