"""Registry tests.

The registry is the platform's extension point, so these tests focus on
the guarantee that matters: an arbitrary new indicator can be registered
and resolved without any engine, service, or API change.
"""

import pytest

from app.indicators.base import (
    Indicator,
    IndicatorContext,
    IndicatorMetadata,
    IndicatorOutput,
    IndicatorSeries,
)
from app.indicators.errors import DuplicateIndicatorError, IndicatorNotFoundError
from app.indicators.registry import IndicatorRegistry


def make_indicator(name: str, category: str = "trend") -> type[Indicator]:
    """Build a minimal valid indicator class for registration tests."""

    class _Stub(Indicator):
        metadata = IndicatorMetadata(
            name=name,
            label=name.upper(),
            description="Stub.",
            category=category,
        )

        def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
            values: list[float | None] = [1.0] * len(ctx.candles)
            return IndicatorOutput(
                series=[IndicatorSeries(name=name, label=name.upper(), values=values)]
            )

    return _Stub


class TestRegistration:
    def test_registers_and_resolves_an_indicator_by_name(self) -> None:
        registry = IndicatorRegistry()
        registry.register(make_indicator("alpha"))
        assert registry.get("alpha").metadata.name == "alpha"

    def test_works_as_a_decorator_returning_the_class_unchanged(self) -> None:
        registry = IndicatorRegistry()
        cls = make_indicator("alpha")
        assert registry.register(cls) is cls

    def test_registers_an_arbitrary_new_indicator_with_no_engine_change(self) -> None:
        # The whole point of the pattern: the registry has no knowledge of
        # any particular indicator, so a brand-new one just works.
        registry = IndicatorRegistry()
        registry.register(make_indicator("brand_new_thing", category="experimental"))
        assert registry.has("brand_new_thing")
        assert registry.get("brand_new_thing").metadata.category == "experimental"

    def test_rejects_a_duplicate_name(self) -> None:
        registry = IndicatorRegistry()
        registry.register(make_indicator("alpha"))
        with pytest.raises(DuplicateIndicatorError, match="already registered"):
            registry.register(make_indicator("alpha"))

    def test_rejects_a_class_without_metadata(self) -> None:
        class NoMetadata(Indicator):
            def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
                raise NotImplementedError

        registry = IndicatorRegistry()
        with pytest.raises(TypeError, match="must declare a class-level"):
            registry.register(NoMetadata)

    def test_instantiates_each_indicator_exactly_once(self) -> None:
        registry = IndicatorRegistry()
        registry.register(make_indicator("alpha"))
        # Indicators are stateless, so the same instance serves every request.
        assert registry.get("alpha") is registry.get("alpha")


class TestLookup:
    def test_raises_a_domain_error_for_an_unknown_name(self) -> None:
        registry = IndicatorRegistry()
        with pytest.raises(IndicatorNotFoundError) as exc_info:
            registry.get("nope")
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "indicator_not_found"

    def test_lists_the_available_names_in_the_not_found_message(self) -> None:
        registry = IndicatorRegistry()
        registry.register(make_indicator("alpha"))
        registry.register(make_indicator("beta"))
        with pytest.raises(IndicatorNotFoundError, match="available: alpha, beta"):
            registry.get("nope")

    def test_has_reports_membership_without_raising(self) -> None:
        registry = IndicatorRegistry()
        registry.register(make_indicator("alpha"))
        assert registry.has("alpha") is True
        assert registry.has("nope") is False


class TestCatalogue:
    def test_names_are_sorted_for_a_stable_catalogue_order(self) -> None:
        registry = IndicatorRegistry()
        for name in ("zulu", "alpha", "mike"):
            registry.register(make_indicator(name))
        assert registry.names() == ("alpha", "mike", "zulu")

    def test_describe_all_returns_metadata_in_the_same_sorted_order(self) -> None:
        registry = IndicatorRegistry()
        for name in ("zulu", "alpha"):
            registry.register(make_indicator(name))
        assert [entry.name for entry in registry.describe_all()] == ["alpha", "zulu"]

    def test_supports_len_and_iteration(self) -> None:
        registry = IndicatorRegistry()
        registry.register(make_indicator("alpha"))
        registry.register(make_indicator("beta"))
        assert len(registry) == 2
        assert [indicator.metadata.name for indicator in registry] == ["alpha", "beta"]

    def test_a_fresh_registry_is_empty(self) -> None:
        registry = IndicatorRegistry()
        assert len(registry) == 0
        assert registry.names() == ()


class TestIsolation:
    def test_two_registries_do_not_share_state(self) -> None:
        # Isolation is what lets a future caller (a backtest pinned to a
        # fixed indicator set) build its own catalogue without disturbing
        # the application's.
        first = IndicatorRegistry()
        second = IndicatorRegistry()
        first.register(make_indicator("alpha"))
        assert first.has("alpha")
        assert not second.has("alpha")
