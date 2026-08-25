"""Validation rule registry tests — registration, duplicates, lookup, catalogue order.

Mirrors ``tests/features/test_registry.py``'s structure: rules are
registered against an isolated, instantiable registry rather than the
application's real one, so a throwaway test rule never leaks into the real
catalogue.
"""

import pytest

from app.dataset_validation.base import (
    ValidationContext,
    ValidationIssue,
    ValidationRule,
    ValidationRuleMetadata,
)
from app.dataset_validation.errors import DuplicateValidationRuleError, UnknownValidationRuleError
from app.dataset_validation.registry import ValidationRuleRegistry


def make_rule(name: str, category: str = "structural") -> type[ValidationRule]:
    """A throwaway rule class that never finds any issue."""

    class _Rule(ValidationRule):
        metadata = ValidationRuleMetadata(name=name, category=category, description="test rule")

        def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
            del ctx
            return []

    _Rule.__name__ = f"Rule_{name}"
    return _Rule


class TestRegistration:
    def test_registers_a_rule_class(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(make_rule("alpha"))
        assert registry.has("alpha")

    def test_decorator_returns_the_class_unchanged(self) -> None:
        registry = ValidationRuleRegistry()
        cls = make_rule("alpha")
        returned = registry.register(cls)
        assert returned is cls

    def test_rejects_a_duplicate_name(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(make_rule("alpha"))
        with pytest.raises(DuplicateValidationRuleError):
            registry.register(make_rule("alpha"))

    def test_rejects_a_class_with_no_metadata(self) -> None:
        registry = ValidationRuleRegistry()

        class _NoMetadata(ValidationRule):
            def check(self, ctx: ValidationContext) -> list[ValidationIssue]:
                del ctx
                return []

        with pytest.raises(TypeError):
            registry.register(_NoMetadata)


class TestLookup:
    def test_get_resolves_a_registered_rule(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(make_rule("alpha"))
        rule = registry.get("alpha")
        assert rule.metadata.name == "alpha"

    def test_get_raises_for_an_unknown_name(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(make_rule("alpha"))
        with pytest.raises(UnknownValidationRuleError) as exc_info:
            registry.get("nope")
        assert exc_info.value.name == "nope"
        assert "alpha" in str(exc_info.value)

    def test_has_reports_presence(self) -> None:
        registry = ValidationRuleRegistry()
        assert not registry.has("alpha")
        registry.register(make_rule("alpha"))
        assert registry.has("alpha")


class TestCatalogue:
    def test_names_are_sorted(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(make_rule("zeta"))
        registry.register(make_rule("alpha"))
        assert registry.names() == ("alpha", "zeta")

    def test_describe_all_returns_every_rules_metadata(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(make_rule("alpha", category="data_quality"))
        described = registry.describe_all()
        assert len(described) == 1
        assert described[0].category == "data_quality"

    def test_len_and_iteration(self) -> None:
        registry = ValidationRuleRegistry()
        registry.register(make_rule("alpha"))
        registry.register(make_rule("beta"))
        assert len(registry) == 2
        assert {rule.metadata.name for rule in registry} == {"alpha", "beta"}

    def test_isolated_registries_do_not_share_state(self) -> None:
        first = ValidationRuleRegistry()
        second = ValidationRuleRegistry()
        first.register(make_rule("alpha"))
        assert first.has("alpha")
        assert not second.has("alpha")
