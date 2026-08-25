"""Pins that every builtin rule module is auto-discovered and registered.

Mirrors ``tests/features/test_builtin_generators.py``'s discovery test:
adding a rule is supposed to require nothing beyond a new file in
``app/dataset_validation/rules/`` decorated with ``@register`` — this test
is what would fail if that guarantee were ever broken.
"""

from app.dataset_validation.registry import default_registry
from app.dataset_validation.rules import load_builtin_rules

EXPECTED_RULES = {
    "required_columns",
    "data_types",
    "missing_values",
    "duplicate_rows",
    "duplicate_timestamps",
    "nan_values",
    "infinite_values",
    "timestamp_ordering",
    "time_gaps",
    "metadata_consistency",
    "feature_failures",
}

EXPECTED_CATEGORIES = {
    "required_columns": "structural",
    "data_types": "structural",
    "missing_values": "data_quality",
    "duplicate_rows": "data_quality",
    "duplicate_timestamps": "data_quality",
    "nan_values": "data_quality",
    "infinite_values": "data_quality",
    "timestamp_ordering": "time_series",
    "time_gaps": "time_series",
    "metadata_consistency": "feature",
    "feature_failures": "feature",
}


def test_every_expected_rule_is_registered() -> None:
    load_builtin_rules()
    assert set(default_registry.names()) >= EXPECTED_RULES


def test_is_idempotent() -> None:
    load_builtin_rules()
    count_before = len(default_registry)
    load_builtin_rules()
    assert len(default_registry) == count_before


def test_every_rule_is_in_its_expected_category() -> None:
    load_builtin_rules()
    for name, category in EXPECTED_CATEGORIES.items():
        assert default_registry.get(name).metadata.category == category


def test_covers_every_check_named_in_the_requirements() -> None:
    """One rule per named check: columns, dtypes, nulls/dupes/NaN/Inf, order/gaps, metadata."""
    load_builtin_rules()
    assert len(default_registry) == len(EXPECTED_RULES)
