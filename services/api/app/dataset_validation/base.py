"""The validation rule contract: inputs, outputs, metadata, and the base class.

Mirrors ``app/features/base.py``'s shape deliberately — the same
Strategy + Registry pattern this platform already uses twice (indicators,
features) is reused a third time here rather than inventing a different
extension mechanism for validation rules. A rule receives a single
``ValidationContext`` wrapping an already-built ``FeatureDataset`` and
returns zero or more ``ValidationIssue``\\ s; it never builds a dataset,
loads a candle, or touches the database — that stays the job of
``FeatureDatasetBuilder``/``FeatureService``, which this engine runs
*after*, never beside or instead of.

Named ``app/dataset_validation/`` rather than ``app/validation/`` on
purpose: this platform already has two other things reasonably called
"validation" — ``app/features/validation.py`` (request-time feature
dependency checks, raised inline during a build) and
``app/services/candle_validation.py`` (stored-candle integrity checks, no
REST surface). This is a third, deliberately distinct concern: an
explicit, on-demand quality gate over an already-built dataset, with its
own registry, report schema, and API surface. Distinct names keep the
three from being confused with one another.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from app.features.dataset import FeatureDataset

__all__ = [
    "VALIDATION_CATEGORIES",
    "Severity",
    "ValidationCategory",
    "ValidationContext",
    "ValidationIssue",
    "ValidationRule",
    "ValidationRuleMetadata",
]

#: How serious one finding is. Only "error" fails the quality gate
#: (``ValidationReport.passed``); "warning" and "info" are always reported
#: but never block a dataset from being used — the same three-tier
#: severity convention as a linter, deliberately, since that is exactly the
#: mental model a researcher already has for "should I stop and fix this
#: before I train on it."
Severity = Literal["error", "warning", "info"]

#: The four validation categories every builtin rule is organized under,
#: matching the four workstreams a dataset must pass before it is
#: considered fit for machine learning, backtesting, or research use.
ValidationCategory = Literal["structural", "data_quality", "time_series", "feature"]

#: Every category, in report order — used to seed a report's per-category
#: summary so a category with zero issues still appears (as all-zero)
#: rather than being silently absent from the response.
VALIDATION_CATEGORIES: tuple[ValidationCategory, ...] = (
    "structural",
    "data_quality",
    "time_series",
    "feature",
)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One finding from one rule.

    ``column``/``row_index``/``count`` are optional because not every issue
    is about a specific cell or a countable total — a timestamp-ordering
    violation names a row, a required-column check names neither.
    """

    rule: str
    category: ValidationCategory
    severity: Severity
    code: str
    message: str
    column: str | None = None
    row_index: int | None = None
    count: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ValidationRuleMetadata:
    """Everything the rule catalogue knows about a rule without running it."""

    name: str
    category: ValidationCategory
    description: str
    default_severity: Severity = "error"
    version: str = "1.0.0"


@dataclass(frozen=True, slots=True)
class ValidationContext:
    """Everything a rule is given: the dataset, plus optional caller expectations.

    ``required_columns`` is the one caller-supplied input this engine
    accepts beyond the dataset itself: a researcher who needs specific
    columns for a downstream model (say, ``close`` and ``sma_20``) can name
    them, and ``RequiredColumnsRule`` checks they actually exist — a real,
    usable extension point, even though every other builtin rule needs
    nothing beyond the dataset.
    """

    dataset: FeatureDataset
    required_columns: tuple[str, ...] = ()


class ValidationRule(ABC):
    """Base class for every validation rule (Strategy + Registry).

    A new rule is a subclass that declares ``metadata`` and implements
    ``check``; the registry, engine, service, and API need no changes to
    support it — the identical extension guarantee ``FeatureGenerator`` and
    ``Indicator`` already make on this platform, applied a third time.
    """

    metadata: ClassVar[ValidationRuleMetadata]

    @abstractmethod
    def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
        """Return every issue this rule finds in ``ctx.dataset``.

        Returns an empty list when the dataset passes this rule cleanly —
        never ``None``, so the engine can always extend its issue list
        directly from the result.
        """
