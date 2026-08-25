"""Feature registry tests — the extension point's contract.

Exercises an *isolated* ``FeatureRegistry`` rather than the application's
``default_registry``, so registering a throwaway test generator can never
leak into another test's catalogue.
"""

import pytest

from app.features.base import (
    FeatureColumn,
    FeatureContext,
    FeatureGenerator,
    FeatureMetadata,
    FeatureOutput,
    FeatureSeries,
)
from app.features.errors import (
    DuplicateFeatureError,
    FeatureDependencyCycleError,
    FeatureNotFoundError,
    UnknownFeatureDependencyError,
)
from app.features.registry import FeatureRegistry


def make_generator(name: str, category: str = "test") -> type[FeatureGenerator]:
    """A minimal one-column generator, for registry mechanics only."""

    class _Generator(FeatureGenerator):
        metadata = FeatureMetadata(
            name=name,
            label=name.upper(),
            description="Test generator.",
            category=category,
        )

        def generate(self, ctx: FeatureContext) -> FeatureOutput:
            return FeatureOutput(
                series=[
                    FeatureSeries(
                        column=FeatureColumn(name=name, label=name.upper()),
                        values=[1.0] * len(ctx.candles),
                    )
                ]
            )

    return _Generator


def make_dependent_generator(
    name: str, dependencies: tuple[str, ...] = ()
) -> type[FeatureGenerator]:
    """A generator declaring dependencies, for dependency-graph tests only."""

    class _Generator(FeatureGenerator):
        metadata = FeatureMetadata(
            name=name,
            label=name.upper(),
            description="Test generator.",
            category="test",
            dependencies=dependencies,
        )

        def generate(self, ctx: FeatureContext) -> FeatureOutput:
            return FeatureOutput(series=[])

    return _Generator


class TestRegistration:
    def test_registers_a_generator_class(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_generator("alpha"))
        assert registry.has("alpha")
        assert len(registry) == 1

    def test_returns_the_class_unchanged_so_it_works_as_a_decorator(self) -> None:
        registry = FeatureRegistry()
        cls = make_generator("alpha")
        assert registry.register(cls) is cls

    def test_registers_a_constructed_instance(self) -> None:
        # The adapter path: IndicatorFeature is built, not declared.
        registry = FeatureRegistry()
        instance = make_generator("alpha")()
        assert registry.register_generator(instance) is instance
        assert registry.get("alpha") is instance

    def test_rejects_a_class_without_metadata(self) -> None:
        registry = FeatureRegistry()

        class NoMetadata(FeatureGenerator):
            def generate(self, ctx: FeatureContext) -> FeatureOutput:  # pragma: no cover
                raise AssertionError("never called")

        with pytest.raises(TypeError, match="metadata"):
            registry.register(NoMetadata)

    def test_rejects_an_instance_without_metadata(self) -> None:
        registry = FeatureRegistry()

        class NoMetadata:
            pass

        with pytest.raises(TypeError, match="metadata"):
            registry.register_generator(NoMetadata())  # type: ignore[arg-type]

    def test_rejects_a_duplicate_name(self) -> None:
        # A programming mistake that must fail fast at import time, never a
        # condition an HTTP client can trigger.
        registry = FeatureRegistry()
        registry.register(make_generator("alpha"))
        with pytest.raises(DuplicateFeatureError, match="alpha"):
            registry.register(make_generator("alpha"))


class TestLookup:
    def test_resolves_a_registered_generator(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_generator("alpha"))
        assert registry.get("alpha").metadata.name == "alpha"

    def test_raises_a_404_domain_error_for_an_unknown_name(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_generator("alpha"))
        with pytest.raises(FeatureNotFoundError) as exc_info:
            registry.get("nope")
        assert exc_info.value.status_code == 404
        assert "alpha" in exc_info.value.message  # lists what *is* available

    def test_has_reports_membership_without_raising(self) -> None:
        registry = FeatureRegistry()
        assert registry.has("nope") is False


class TestCatalogue:
    def test_names_are_sorted_for_a_stable_catalogue_order(self) -> None:
        registry = FeatureRegistry()
        for name in ("zulu", "alpha", "mike"):
            registry.register(make_generator(name))
        assert registry.names() == ("alpha", "mike", "zulu")

    def test_describe_all_returns_metadata_in_name_order(self) -> None:
        registry = FeatureRegistry()
        for name in ("zulu", "alpha"):
            registry.register(make_generator(name))
        assert [entry.name for entry in registry.describe_all()] == ["alpha", "zulu"]

    def test_iterates_generators_in_name_order(self) -> None:
        registry = FeatureRegistry()
        for name in ("zulu", "alpha"):
            registry.register(make_generator(name))
        assert [g.metadata.name for g in registry] == ["alpha", "zulu"]

    def test_isolated_registries_do_not_share_state(self) -> None:
        # Why the registry is instantiable rather than a module singleton:
        # a training run pinned to a fixed feature set must be able to build
        # its own catalogue without touching the application's.
        first = FeatureRegistry()
        second = FeatureRegistry()
        first.register(make_generator("alpha"))
        assert second.has("alpha") is False


class TestDependencyValidation:
    """The startup-time integrity check over the whole registry's dependency graph.

    Distinct from `validate_feature_requests` (`test_validation.py`), which
    checks one *request*; this checks the graph every registered generator's
    own declarations form, once, regardless of what anyone ever requests.
    """

    def test_passes_for_a_registry_with_no_dependencies(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_generator("alpha"))
        registry.validate_dependencies()  # must not raise

    def test_passes_for_a_valid_dependency_chain(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_dependent_generator("base"))
        registry.register(make_dependent_generator("derived", dependencies=("base",)))
        registry.validate_dependencies()  # must not raise

    def test_rejects_a_dependency_on_an_unregistered_feature(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_dependent_generator("orphan", dependencies=("ghost",)))
        with pytest.raises(UnknownFeatureDependencyError) as exc_info:
            registry.validate_dependencies()
        assert exc_info.value.feature == "orphan"
        assert exc_info.value.unknown == ("ghost",)

    def test_rejects_a_direct_self_dependency(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_dependent_generator("loopy", dependencies=("loopy",)))
        with pytest.raises(FeatureDependencyCycleError) as exc_info:
            registry.validate_dependencies()
        assert exc_info.value.cycle == ("loopy", "loopy")

    def test_rejects_a_two_node_cycle(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_dependent_generator("a", dependencies=("b",)))
        registry.register(make_dependent_generator("b", dependencies=("a",)))
        with pytest.raises(FeatureDependencyCycleError) as exc_info:
            registry.validate_dependencies()
        assert set(exc_info.value.cycle) == {"a", "b"}

    def test_rejects_a_longer_cycle(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_dependent_generator("a", dependencies=("b",)))
        registry.register(make_dependent_generator("b", dependencies=("c",)))
        registry.register(make_dependent_generator("c", dependencies=("a",)))
        with pytest.raises(FeatureDependencyCycleError):
            registry.validate_dependencies()

    def test_a_shared_dependency_used_by_two_features_is_not_a_cycle(self) -> None:
        # Two generators depending on the same base feature is the normal
        # case (a future "returns" and "volatility" feature both reading
        # `ohlcv`, say) — the graph is a DAG, not a cycle.
        registry = FeatureRegistry()
        registry.register(make_dependent_generator("base"))
        registry.register(make_dependent_generator("left", dependencies=("base",)))
        registry.register(make_dependent_generator("right", dependencies=("base",)))
        registry.validate_dependencies()  # must not raise
