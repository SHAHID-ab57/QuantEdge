"""Dataset validator (engine) tests — running rules, summarizing, the pass/fail verdict.

Uses an isolated registry of throwaway rules rather than the application's
real builtin ones, so this file tests the *engine's* behaviour (does it run
every rule, does one error fail the gate, does a warning not) independent
of what any specific builtin rule actually checks — those live in
``test_rules_*.py``.
"""

import pytest

from app.dataset_validation.base import (
    VALIDATION_CATEGORIES,
    ValidationContext,
    ValidationIssue,
    ValidationRule,
    ValidationRuleMetadata,
)
from app.dataset_validation.engine import DatasetValidator
from app.dataset_validation.errors import UnknownValidationRuleError
from app.dataset_validation.registry import ValidationRuleRegistry
from tests.dataset_validation.conftest import make_dataset


def rule_emitting(name: str, severity: str, category: str = "structural") -> type[ValidationRule]:
    """A rule that always emits exactly one issue at the given severity."""

    class _Rule(ValidationRule):
        metadata = ValidationRuleMetadata(name=name, category=category, description="test")

        def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
            del ctx
            return [
                ValidationIssue(
                    rule=name,
                    category=category,
                    severity=severity,
                    code=f"{name}_issue",
                    message="always fires",
                )
            ]

    _Rule.__name__ = f"Rule_{name}"
    return _Rule


def clean_rule(name: str, category: str = "structural") -> type[ValidationRule]:
    """A rule that never finds anything."""

    class _Rule(ValidationRule):
        metadata = ValidationRuleMetadata(name=name, category=category, description="test")

        def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
            del ctx
            return []

    _Rule.__name__ = f"Rule_{name}"
    return _Rule


class TestPassFail:
    def test_passes_when_no_rule_finds_an_error(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(rule_emitting("warns", "warning"))
        registry.register(clean_rule("clean"))
        report = DatasetValidator(registry).validate(make_dataset())
        assert report.passed is True
        assert report.summary.errors == 0
        assert report.summary.warnings == 1

    def test_fails_when_any_rule_finds_an_error(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(rule_emitting("breaks", "error"))
        registry.register(clean_rule("clean"))
        report = DatasetValidator(registry).validate(make_dataset())
        assert report.passed is False
        assert report.summary.errors == 1

    def test_info_severity_never_fails_the_gate(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(rule_emitting("notes", "info"))
        report = DatasetValidator(registry).validate(make_dataset())
        assert report.passed is True
        assert report.summary.info == 1


class TestRuleSelection:
    def test_runs_every_registered_rule_by_default(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(clean_rule("alpha"))
        registry.register(clean_rule("beta"))
        report = DatasetValidator(registry).validate(make_dataset())
        assert set(report.rules_run) == {"alpha", "beta"}

    def test_runs_only_the_named_subset(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(rule_emitting("alpha", "error"))
        registry.register(rule_emitting("beta", "error"))
        report = DatasetValidator(registry).validate(make_dataset(), rules=("alpha",))
        assert report.rules_run == ("alpha",)
        assert report.summary.errors == 1

    def test_an_unknown_rule_name_raises(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(clean_rule("alpha"))
        with pytest.raises(UnknownValidationRuleError):
            DatasetValidator(registry).validate(make_dataset(), rules=("nope",))


class TestCategorySummary:
    def test_every_category_is_present_even_at_zero(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(clean_rule("alpha"))
        report = DatasetValidator(registry).validate(make_dataset())
        assert set(report.categories) == set(VALIDATION_CATEGORIES)
        assert report.categories["time_series"].errors == 0

    def test_counts_are_scoped_to_their_own_category(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(rule_emitting("structural_issue", "error", category="structural"))
        registry.register(rule_emitting("quality_issue", "warning", category="data_quality"))
        report = DatasetValidator(registry).validate(make_dataset())
        assert report.categories["structural"].errors == 1
        assert report.categories["structural"].warnings == 0
        assert report.categories["data_quality"].warnings == 1
        assert report.categories["data_quality"].errors == 0


class TestReportShape:
    def test_carries_the_datasets_own_identity(self) -> None:
        registry = ValidationRuleRegistry()
        dataset = make_dataset(dataset_id="my-id", symbol="BTCUSD", timeframe="4h")
        report = DatasetValidator(registry).validate(dataset)
        assert report.dataset_id == "my-id"
        assert report.symbol == "BTCUSD"
        assert report.timeframe == "4h"

    def test_reports_rows_and_columns(self) -> None:
        registry = ValidationRuleRegistry()
        dataset = make_dataset()
        report = DatasetValidator(registry).validate(dataset)
        assert report.rows == dataset.row_count
        assert report.columns == len(dataset.columns)

    def test_duration_is_measured(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(clean_rule("alpha"))
        report = DatasetValidator(registry).validate(make_dataset())
        assert report.duration_ms >= 0.0
