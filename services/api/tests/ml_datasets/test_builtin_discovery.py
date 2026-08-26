"""Pins that every builtin target module is auto-discovered and registered.

Mirrors `tests/features/test_builtin_generators.py`'s discovery test:
adding a target is supposed to require nothing beyond a new file in
`app/ml_datasets/targets/` decorated with `@register`.
"""

from app.ml_datasets.registry import default_registry
from app.ml_datasets.targets import load_builtin_targets

EXPECTED_TARGETS = {"next_close", "next_direction", "next_return"}


def test_every_expected_target_is_registered() -> None:
    load_builtin_targets()
    assert set(default_registry.names()) >= EXPECTED_TARGETS


def test_is_idempotent() -> None:
    load_builtin_targets()
    count_before = len(default_registry)
    load_builtin_targets()
    assert len(default_registry) == count_before


def test_every_builtin_declares_the_horizon_parameter() -> None:
    """Every builtin target accepts the shared `horizon` parameter."""
    load_builtin_targets()
    for name in EXPECTED_TARGETS:
        metadata = default_registry.get(name).metadata
        assert any(spec.name == "horizon" for spec in metadata.parameters)


def test_every_builtin_publishes_usable_output_templates() -> None:
    load_builtin_targets()
    for name in EXPECTED_TARGETS:
        metadata = default_registry.get(name).metadata
        assert len(metadata.outputs) >= 1
