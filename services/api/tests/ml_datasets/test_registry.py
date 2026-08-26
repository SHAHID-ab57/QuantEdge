"""Target registry tests — registration, duplicates, lookup, catalogue order."""

import pytest

from app.ml_datasets.base import TargetContext, TargetGenerator, TargetMetadata, TargetOutput
from app.ml_datasets.errors import DuplicateTargetError, TargetNotFoundError
from app.ml_datasets.registry import TargetRegistry


def make_generator(name: str, category: str = "test") -> type[TargetGenerator]:
    """A throwaway target generator that produces no output columns."""

    class _Generator(TargetGenerator):
        metadata = TargetMetadata(name=name, label=name, description="", category=category)

        def generate(self, ctx: TargetContext) -> TargetOutput:
            return TargetOutput(series=[])

    _Generator.__name__ = f"Generator_{name}"
    return _Generator


class TestRegistration:
    def test_registers_a_generator_class(self) -> None:
        registry = TargetRegistry()
        registry.register(make_generator("alpha"))
        assert registry.has("alpha")

    def test_decorator_returns_the_class_unchanged(self) -> None:
        registry = TargetRegistry()
        cls = make_generator("alpha")
        assert registry.register(cls) is cls

    def test_rejects_a_duplicate_name(self) -> None:
        registry = TargetRegistry()
        registry.register(make_generator("alpha"))
        with pytest.raises(DuplicateTargetError):
            registry.register(make_generator("alpha"))

    def test_rejects_a_class_with_no_metadata(self) -> None:
        registry = TargetRegistry()

        class _NoMetadata(TargetGenerator):
            def generate(self, ctx: TargetContext) -> TargetOutput:
                return TargetOutput(series=[])

        with pytest.raises(TypeError):
            registry.register(_NoMetadata)


class TestLookup:
    def test_get_resolves_a_registered_generator(self) -> None:
        registry = TargetRegistry()
        registry.register(make_generator("alpha"))
        assert registry.get("alpha").metadata.name == "alpha"

    def test_get_raises_for_an_unknown_name(self) -> None:
        registry = TargetRegistry()
        registry.register(make_generator("alpha"))
        with pytest.raises(TargetNotFoundError) as exc_info:
            registry.get("nope")
        assert exc_info.value.name == "nope"
        assert "alpha" in str(exc_info.value)

    def test_has_reports_presence(self) -> None:
        registry = TargetRegistry()
        assert not registry.has("alpha")
        registry.register(make_generator("alpha"))
        assert registry.has("alpha")


class TestCatalogue:
    def test_names_are_sorted(self) -> None:
        registry = TargetRegistry()
        registry.register(make_generator("zeta"))
        registry.register(make_generator("alpha"))
        assert registry.names() == ("alpha", "zeta")

    def test_describe_all_returns_every_generators_metadata(self) -> None:
        registry = TargetRegistry()
        registry.register(make_generator("alpha", category="direction"))
        described = registry.describe_all()
        assert len(described) == 1
        assert described[0].category == "direction"

    def test_len_and_iteration(self) -> None:
        registry = TargetRegistry()
        registry.register(make_generator("alpha"))
        registry.register(make_generator("beta"))
        assert len(registry) == 2
        assert {generator.metadata.name for generator in registry} == {"alpha", "beta"}

    def test_isolated_registries_do_not_share_state(self) -> None:
        first = TargetRegistry()
        second = TargetRegistry()
        first.register(make_generator("alpha"))
        assert first.has("alpha")
        assert not second.has("alpha")
