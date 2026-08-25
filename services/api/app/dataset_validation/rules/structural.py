"""Structural validation: required columns and declared data types.

Both rules check the dataset's own shape against what it claims to be — do
the columns it says exist actually exist, and does every value match its
column's declared ``dtype``. This is the same "is the shape what it says it
is" concern ``app/features/dataset.py``'s column-collision check already
guards *during* a build; this is that concern re-checked as an explicit,
standalone gate a caller can run on demand, over the dataset as delivered.
"""

from app.dataset_validation.base import (
    ValidationContext,
    ValidationIssue,
    ValidationRule,
    ValidationRuleMetadata,
)
from app.dataset_validation.registry import register

#: bool is a subclass of int in Python, so a "float"/"int" dtype check must
#: exclude it explicitly or every boolean would silently pass as numeric.
_NUMERIC_TYPES = (int, float)


@register
class RequiredColumnsRule(ValidationRule):
    """Every caller-required column, and every feature's declared output, exists."""

    metadata = ValidationRuleMetadata(
        name="required_columns",
        category="structural",
        description=(
            "Every caller-supplied `required_columns` name, and every column a requested "
            "feature declares producing, is actually present in the dataset"
        ),
        default_severity="error",
    )

    def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
        dataset = ctx.dataset
        present = {column.name for column in dataset.columns}
        issues: list[ValidationIssue] = []

        for name in ctx.required_columns:
            if name not in present:
                issues.append(
                    ValidationIssue(
                        rule=self.metadata.name,
                        category=self.metadata.category,
                        severity="error",
                        code="missing_required_column",
                        message=f"Required column {name!r} is not present in this dataset",
                        column=name,
                    )
                )

        for info in dataset.features:
            for name in info.columns:
                if name not in present:
                    issues.append(
                        ValidationIssue(
                            rule=self.metadata.name,
                            category=self.metadata.category,
                            severity="error",
                            code="missing_declared_column",
                            message=(
                                f"Feature {info.feature!r} declares column {name!r} but it "
                                "is not present among the dataset's columns"
                            ),
                            column=name,
                        )
                    )
        return issues


@register
class DataTypesRule(ValidationRule):
    """Every cell matches its column's declared ``dtype``."""

    metadata = ValidationRuleMetadata(
        name="data_types",
        category="structural",
        description="Every column's cell values match its declared dtype",
        default_severity="error",
    )

    def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
        dataset = ctx.dataset
        issues: list[ValidationIssue] = []
        for index, column in enumerate(dataset.columns):
            mismatches = sum(
                1
                for row in dataset.rows
                if row[index] is not None and not _matches_dtype(row[index], column.dtype)
            )
            if mismatches:
                issues.append(
                    ValidationIssue(
                        rule=self.metadata.name,
                        category=self.metadata.category,
                        severity="error",
                        code="column_dtype_mismatch",
                        message=(
                            f"Column {column.name!r} declares dtype {column.dtype!r} but "
                            f"{mismatches} value(s) do not match it"
                        ),
                        column=column.name,
                        count=mismatches,
                    )
                )
        return issues


def _matches_dtype(value: object, dtype: str) -> bool:
    """Whether ``value`` is a legal cell for a column declaring ``dtype``.

    Unknown/future dtypes fall through as valid rather than flagged — a
    dtype this rule doesn't yet recognize is not evidence of corrupt data.
    """
    if dtype == "bool":
        return isinstance(value, bool)
    if dtype in ("float", "int"):
        return isinstance(value, _NUMERIC_TYPES) and not isinstance(value, bool)
    if dtype == "categorical":
        return isinstance(value, str)
    return True
