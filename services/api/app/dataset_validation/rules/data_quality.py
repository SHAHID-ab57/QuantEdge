"""Data quality validation: missing values, duplicate rows/timestamps, NaN, and infinities.

``DuplicateTimestampsRule`` reuses ``count_duplicate_timestamps`` from
``app/features/quality.py`` rather than reimplementing duplicate-counting a
third time on this platform (the dataset builder's own quality report and
``candle_validation.py`` each already have one, for their own different
scopes — see ``quality.py``'s module docstring for how those two differ).
Every other rule here checks something none of those already compute: null
counts on the *delivered* rows (not the pre-warmup-trim ones the dataset's
own quality report counts — a caller who set ``drop_warmup=false`` gets a
report about the exact series a model would actually receive), whole-row
duplication, and NaN/Infinity, which are distinct failure modes from a
plain missing (``None``) value and from each other.
"""

import math

from app.dataset_validation.base import (
    ValidationContext,
    ValidationIssue,
    ValidationRule,
    ValidationRuleMetadata,
)
from app.dataset_validation.registry import register
from app.features.quality import count_duplicate_timestamps


@register
class MissingValuesRule(ValidationRule):
    """Null cells in the *delivered* dataset — what a consumer would actually receive."""

    metadata = ValidationRuleMetadata(
        name="missing_values",
        category="data_quality",
        description="Null cell counts per column in the delivered rows",
        default_severity="warning",
    )

    def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
        dataset = ctx.dataset
        counts = {column.name: 0 for column in dataset.columns}
        for row in dataset.rows:
            for column, value in zip(dataset.columns, row, strict=True):
                if value is None:
                    counts[column.name] += 1
        return [
            ValidationIssue(
                rule=self.metadata.name,
                category=self.metadata.category,
                severity="warning",
                code="missing_values",
                message=(f"Column {name!r} has {count} missing value(s) in the delivered dataset"),
                column=name,
                count=count,
            )
            for name, count in counts.items()
            if count
        ]


@register
class DuplicateRowsRule(ValidationRule):
    """Whole rows (every column's value identical) appearing more than once."""

    metadata = ValidationRuleMetadata(
        name="duplicate_rows",
        category="data_quality",
        description="Rows whose every value is identical to an earlier row",
        default_severity="warning",
    )

    def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
        seen: set[tuple[object, ...]] = set()
        duplicates = 0
        for row in ctx.dataset.rows:
            key = tuple(row)
            if key in seen:
                duplicates += 1
            else:
                seen.add(key)
        if not duplicates:
            return []
        return [
            ValidationIssue(
                rule=self.metadata.name,
                category=self.metadata.category,
                severity="warning",
                code="duplicate_rows",
                message=f"{duplicates} row(s) are exact duplicates of an earlier row",
                count=duplicates,
            )
        ]


@register
class DuplicateTimestampsRule(ValidationRule):
    """Timestamps appearing more than once in the delivered dataset."""

    metadata = ValidationRuleMetadata(
        name="duplicate_timestamps",
        category="data_quality",
        description="Timestamps appearing more than once in the delivered dataset",
        default_severity="error",
    )

    def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
        duplicates = count_duplicate_timestamps(ctx.dataset.timestamps)
        if not duplicates:
            return []
        return [
            ValidationIssue(
                rule=self.metadata.name,
                category=self.metadata.category,
                severity="error",
                code="duplicate_timestamps",
                message=(
                    f"{duplicates} timestamp(s) appear more than once — each row must be "
                    "uniquely timestamped"
                ),
                count=duplicates,
            )
        ]


@register
class NaNValuesRule(ValidationRule):
    """Float ``NaN`` cells — a distinct failure mode from a missing (``None``) value."""

    metadata = ValidationRuleMetadata(
        name="nan_values",
        category="data_quality",
        description="Float NaN cells, which a missing-values check alone would not catch",
        default_severity="error",
    )

    def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
        dataset = ctx.dataset
        counts = {column.name: 0 for column in dataset.columns}
        for row in dataset.rows:
            for column, value in zip(dataset.columns, row, strict=True):
                if isinstance(value, float) and math.isnan(value):
                    counts[column.name] += 1
        return [
            ValidationIssue(
                rule=self.metadata.name,
                category=self.metadata.category,
                severity="error",
                code="nan_values",
                message=f"Column {name!r} contains {count} NaN value(s)",
                column=name,
                count=count,
            )
            for name, count in counts.items()
            if count
        ]


@register
class InfiniteValuesRule(ValidationRule):
    """Float ``inf``/``-inf`` cells."""

    metadata = ValidationRuleMetadata(
        name="infinite_values",
        category="data_quality",
        description="Float positive or negative infinity cells",
        default_severity="error",
    )

    def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
        dataset = ctx.dataset
        counts = {column.name: 0 for column in dataset.columns}
        for row in dataset.rows:
            for column, value in zip(dataset.columns, row, strict=True):
                if isinstance(value, float) and math.isinf(value):
                    counts[column.name] += 1
        return [
            ValidationIssue(
                rule=self.metadata.name,
                category=self.metadata.category,
                severity="error",
                code="infinite_values",
                message=f"Column {name!r} contains {count} infinite value(s)",
                column=name,
                count=count,
            )
            for name, count in counts.items()
            if count
        ]
