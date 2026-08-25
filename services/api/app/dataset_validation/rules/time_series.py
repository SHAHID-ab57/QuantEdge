"""Time-series validation: timestamp ordering and gaps.

``TimeGapsRule`` reuses ``count_missing_candles`` from
``app/features/quality.py`` (itself built on ``resolution_duration``,
shared platform-wide) rather than re-declaring a third timeframe-to-
bucket-length mapping — it is simply called over the *delivered* dataset's
timestamps instead of the pre-trim candle range the dataset's own quality
report covers, a genuinely different (and still useful) scope: a caller
who set ``drop_warmup=false`` gets a report about the exact series a model
would actually see, gaps included.
"""

from app.dataset_validation.base import (
    ValidationContext,
    ValidationIssue,
    ValidationRule,
    ValidationRuleMetadata,
)
from app.dataset_validation.registry import register
from app.features.quality import count_missing_candles


@register
class TimestampOrderingRule(ValidationRule):
    """Timestamps must be strictly increasing."""

    metadata = ValidationRuleMetadata(
        name="timestamp_ordering",
        category="time_series",
        description="Timestamps are in strictly increasing chronological order",
        default_severity="error",
    )

    def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
        timestamps = ctx.dataset.timestamps
        violations = 0
        first_index: int | None = None
        for index in range(1, len(timestamps)):
            if timestamps[index] <= timestamps[index - 1]:
                violations += 1
                if first_index is None:
                    first_index = index
        if not violations:
            return []
        return [
            ValidationIssue(
                rule=self.metadata.name,
                category=self.metadata.category,
                severity="error",
                code="timestamp_ordering",
                message=(
                    f"{violations} row(s) are out of chronological order "
                    f"(first at row {first_index})"
                ),
                row_index=first_index,
                count=violations,
            )
        ]


@register
class TimeGapsRule(ValidationRule):
    """Gaps in the delivered series at the timeframe's expected cadence."""

    metadata = ValidationRuleMetadata(
        name="time_gaps",
        category="time_series",
        description="Gaps in the delivered timestamp series at the timeframe's cadence",
        default_severity="warning",
    )

    def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
        dataset = ctx.dataset
        missing = count_missing_candles(dataset.timestamps, dataset.timeframe)
        if not missing:
            return []
        return [
            ValidationIssue(
                rule=self.metadata.name,
                category=self.metadata.category,
                severity="warning",
                code="time_gaps",
                message=(
                    f"{missing} expected {dataset.timeframe} interval(s) are missing from "
                    "the delivered series"
                ),
                count=missing,
            )
        ]
