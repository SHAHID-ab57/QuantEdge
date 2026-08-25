"""The dataset validator — runs every applicable rule and assembles a report.

Mirrors ``FeaturePipeline``'s shape: a fixed, unbranched execution sequence
("run every rule, collect every issue, summarize") rather than a
hand-written if/elif per rule, so registering a new ``ValidationRule``
makes it run with no change to this module.
"""

import logging
from datetime import UTC, datetime
from time import perf_counter

from app.dataset_validation.base import VALIDATION_CATEGORIES, ValidationContext, ValidationIssue
from app.dataset_validation.registry import ValidationRuleRegistry
from app.dataset_validation.report import CategorySummary, ValidationReport, ValidationSummary
from app.features.dataset import FeatureDataset

logger = logging.getLogger("app.dataset_validation.engine")

#: Versions the *execution pipeline itself* — independent of any single
#: rule's own ``ValidationRuleMetadata.version`` — so a researcher comparing
#: reports across time can tell whether the engine changed underneath them,
#: not just a rule. Mirrors ``app.indicators.engine.ENGINE_VERSION`` and
#: ``app.features.pipeline.PIPELINE_VERSION``.
ENGINE_VERSION = "1.0.0"


class DatasetValidator:
    """Runs every registered rule (or a caller-chosen subset) over a dataset."""

    def __init__(self, registry: ValidationRuleRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> ValidationRuleRegistry:
        """The registry this validator draws rules from."""
        return self._registry

    def validate(
        self,
        dataset: FeatureDataset,
        *,
        required_columns: tuple[str, ...] = (),
        rules: tuple[str, ...] | None = None,
    ) -> ValidationReport:
        """Run every rule named in ``rules`` (or every registered rule) over ``dataset``.

        An unknown name in ``rules`` raises ``UnknownValidationRuleError``
        (via the registry's own ``get``) before anything runs — a caller
        who mistypes a rule name gets a clear 404 naming every valid
        option, not a silently incomplete report.
        """
        names = rules if rules is not None else self._registry.names()
        ctx = ValidationContext(dataset=dataset, required_columns=required_columns)

        started = perf_counter()
        issues: list[ValidationIssue] = []
        for name in names:
            rule = self._registry.get(name)
            issues.extend(rule.check(ctx))
        duration_ms = (perf_counter() - started) * 1000

        summary = _summarize(issues)
        categories = _summarize_categories(issues)
        passed = summary.errors == 0

        logger.info(
            "Validated dataset %s (rules=%d issues=%d errors=%d warnings=%d passed=%s)",
            dataset.dataset_id,
            len(names),
            len(issues),
            summary.errors,
            summary.warnings,
            passed,
        )

        return ValidationReport(
            dataset_id=dataset.dataset_id,
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            engine_version=ENGINE_VERSION,
            validated_at=datetime.now(UTC),
            passed=passed,
            rules_run=tuple(names),
            summary=summary,
            categories=categories,
            issues=tuple(issues),
            rows=dataset.row_count,
            columns=len(dataset.columns),
            duration_ms=duration_ms,
        )


def _summarize(issues: list[ValidationIssue]) -> ValidationSummary:
    """Headline counts across every issue, regardless of category."""
    errors = sum(1 for issue in issues if issue.severity == "error")
    warnings = sum(1 for issue in issues if issue.severity == "warning")
    info = sum(1 for issue in issues if issue.severity == "info")
    return ValidationSummary(total_checks=len(issues), errors=errors, warnings=warnings, info=info)


def _summarize_categories(issues: list[ValidationIssue]) -> dict[str, CategorySummary]:
    """Per-category counts, seeded at zero for every category up front.

    Seeding every category (rather than only ones with an issue) is what
    lets a frontend summary card render "Time-Series: 0 errors" instead of
    omitting the category entirely when nothing was wrong.
    """
    counts: dict[str, dict[str, int]] = {
        category: {"errors": 0, "warnings": 0, "info": 0} for category in VALIDATION_CATEGORIES
    }
    for issue in issues:
        bucket = counts[issue.category]
        key = f"{issue.severity}s" if issue.severity != "info" else "info"
        bucket[key] += 1
    return {category: CategorySummary(**values) for category, values in counts.items()}
