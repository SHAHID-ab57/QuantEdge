"""Feature validation: cross-checking the dataset against its own provenance record.

Both rules read fields the dataset builder already computed
(``dataset.quality.feature_failures``, ``DatasetFeatureInfo``, row/column
counts) rather than recomputing anything — this category exists to check
that the dataset *agrees with itself*, not to recompute what the builder
already knows.
"""

from app.dataset_validation.base import (
    ValidationContext,
    ValidationIssue,
    ValidationRule,
    ValidationRuleMetadata,
)
from app.dataset_validation.registry import register


@register
class MetadataConsistencyRule(ValidationRule):
    """The dataset's row/column counts and provenance record agree with themselves."""

    metadata = ValidationRuleMetadata(
        name="metadata_consistency",
        category="feature",
        description="Row/column counts and quality-report totals are internally consistent",
        default_severity="error",
    )

    def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
        dataset = ctx.dataset
        issues: list[ValidationIssue] = []

        if len(dataset.timestamps) != len(dataset.rows):
            issues.append(
                ValidationIssue(
                    rule=self.metadata.name,
                    category=self.metadata.category,
                    severity="error",
                    code="row_timestamp_mismatch",
                    message=(
                        f"{len(dataset.timestamps)} timestamps but {len(dataset.rows)} rows "
                        "— these must be the same length"
                    ),
                )
            )

        for row_index, row in enumerate(dataset.rows):
            if len(row) != len(dataset.columns):
                issues.append(
                    ValidationIssue(
                        rule=self.metadata.name,
                        category=self.metadata.category,
                        severity="error",
                        code="row_column_mismatch",
                        message=(
                            f"Row {row_index} has {len(row)} value(s) but the dataset "
                            f"declares {len(dataset.columns)} column(s)"
                        ),
                        row_index=row_index,
                    )
                )
                break  # one instance proves the structural break; more would only repeat it

        if dataset.quality.rows_returned != dataset.row_count:
            issues.append(
                ValidationIssue(
                    rule=self.metadata.name,
                    category=self.metadata.category,
                    severity="error",
                    code="quality_row_count_mismatch",
                    message=(
                        f"quality.rows_returned ({dataset.quality.rows_returned}) does not "
                        f"match the delivered row count ({dataset.row_count})"
                    ),
                )
            )
        return issues


@register
class FeatureFailureRule(ValidationRule):
    """Surfaces any requested feature that failed to generate."""

    metadata = ValidationRuleMetadata(
        name="feature_failures",
        category="feature",
        description="Every requested feature generated successfully",
        default_severity="warning",
    )

    def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                rule=self.metadata.name,
                category=self.metadata.category,
                severity="warning",
                code="feature_generation_failed",
                message=f"Feature {failure.feature!r} failed to generate: {failure.error_detail}",
                details={"error_code": failure.error_code, "params": failure.params},
            )
            for failure in ctx.dataset.quality.feature_failures
        ]
