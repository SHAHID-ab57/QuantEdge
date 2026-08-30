"""Feature lineage / dependency graph tests.

Uses hand-built `FeatureRegistry` instances (never `default_registry`) so
these tests can freely declare real dependencies — no shipped generator
declares one today (see `FeatureMetadata.dependencies`'s own docstring).
"""

import pytest

from app.features.base import FeatureContext, FeatureGenerator, FeatureMetadata, FeatureOutput
from app.features.errors import FeatureDependencyCycleError
from app.features.lineage import build_lineage_graph
from app.features.registry import FeatureRegistry


def make_generator(name: str, dependencies: tuple[str, ...] = ()) -> type[FeatureGenerator]:
    """Build a throwaway generator class declaring the given dependencies."""

    class _Generator(FeatureGenerator):
        metadata = FeatureMetadata(
            name=name,
            label=name.title(),
            description="Test generator.",
            category="test",
            dependencies=dependencies,
        )

        def generate(self, ctx: FeatureContext) -> FeatureOutput:  # pragma: no cover
            raise NotImplementedError

    _Generator.__name__ = f"Generator_{name}"
    return _Generator


class TestNoDependencies:
    """Today's real state: every builtin generator declares no dependency."""

    def test_every_node_has_empty_edges(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_generator("ohlcv"))
        registry.register(make_generator("candle_shape"))

        graph = build_lineage_graph(registry)

        assert graph.edges == []
        for node in graph.nodes:
            assert node.dependencies == ()
            assert node.depended_on_by == ()
            assert node.ancestors == ()
            assert node.descendants == ()

    def test_topological_order_still_includes_every_name(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_generator("ohlcv"))
        registry.register(make_generator("candle_shape"))

        graph = build_lineage_graph(registry)

        assert set(graph.topological_order) == {"ohlcv", "candle_shape"}


class TestWithDependencies:
    def test_direct_dependency_is_recorded_both_ways(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_generator("sma"))
        registry.register(make_generator("bollinger", dependencies=("sma",)))

        graph = build_lineage_graph(registry)
        by_name = {node.name: node for node in graph.nodes}

        assert by_name["bollinger"].dependencies == ("sma",)
        assert by_name["sma"].depended_on_by == ("bollinger",)
        assert ("sma", "bollinger") in graph.edges

    def test_transitive_ancestors_and_descendants_resolve_through_a_chain(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_generator("a"))
        registry.register(make_generator("b", dependencies=("a",)))
        registry.register(make_generator("c", dependencies=("b",)))

        graph = build_lineage_graph(registry)
        by_name = {node.name: node for node in graph.nodes}

        assert by_name["c"].ancestors == ("a", "b")
        assert by_name["a"].descendants == ("b", "c")

    def test_topological_order_places_a_dependency_before_its_dependent(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_generator("a"))
        registry.register(make_generator("b", dependencies=("a",)))

        graph = build_lineage_graph(registry)

        assert graph.topological_order.index("a") < graph.topological_order.index("b")

    def test_a_feature_with_two_dependents_reports_both(self) -> None:
        registry = FeatureRegistry()
        registry.register(make_generator("a"))
        registry.register(make_generator("b", dependencies=("a",)))
        registry.register(make_generator("c", dependencies=("a",)))

        graph = build_lineage_graph(registry)
        by_name = {node.name: node for node in graph.nodes}

        assert by_name["a"].depended_on_by == ("b", "c")

    def test_raises_on_a_cycle_rather_than_looping_forever(self) -> None:
        # Built by hand, bypassing `validate_dependencies` (which would
        # normally catch this at startup) — the defensive case this
        # module's own docstring describes.
        registry = FeatureRegistry()
        registry.register(make_generator("a", dependencies=("b",)))
        registry.register(make_generator("b", dependencies=("a",)))

        with pytest.raises(FeatureDependencyCycleError):
            build_lineage_graph(registry)
