"""Feature lineage / dependency graph — a traversable view over
`FeatureMetadata.dependencies`.

`FeatureRegistry` already validates this graph at startup
(`validate_dependencies`'s unknown-name and cycle checks) and already
publishes the raw edges (`FeatureDTO.dependencies`) — this module is the
one addition on top: resolving the *transitive* closure in both directions
(everything a feature depends on, everything that depends on it) and a
topological order, computed once per request rather than asked of every
caller to derive itself. Deliberately one shared module for both "lineage"
(what feeds this one feature) and "dependency graph" (the whole registry's
structure) — they are the same underlying edge set read two ways, and a
second, parallel graph representation would be exactly the kind of
duplication this platform's Strategy + Registry contexts already avoid.

Assumes the graph is acyclic, which `FeatureRegistry.validate_dependencies`
already guarantees at startup for the process-wide `default_registry` — a
registry that hasn't been validated (e.g. a test building one by hand
without calling it) could in principle contain a cycle, in which case
`_topological_order` raises `FeatureDependencyCycleError` rather than
looping forever, the same integrity failure `validate_dependencies` itself
would have already raised earlier.
"""

from dataclasses import dataclass, field

from app.features.errors import FeatureDependencyCycleError
from app.features.registry import FeatureRegistry


@dataclass(frozen=True, slots=True)
class FeatureLineageNode:
    """One feature's place in the dependency graph."""

    name: str
    label: str
    category: str
    #: Features this one directly depends on (`metadata.dependencies`, verbatim).
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    #: Features that directly depend on this one — the reverse edge, not
    #: declared anywhere; derived here from every other node's `dependencies`.
    depended_on_by: tuple[str, ...] = field(default_factory=tuple)
    #: The full transitive closure of `dependencies` — "everything this
    #: feature ultimately needs," not just its immediate neighbors.
    ancestors: tuple[str, ...] = field(default_factory=tuple)
    #: The full transitive closure of `depended_on_by` — "everything that
    #: would be affected if this feature's output changed."
    descendants: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class FeatureLineageGraph:
    """The whole registry's dependency structure, resolved."""

    nodes: list[FeatureLineageNode] = field(default_factory=list)
    #: `(dependency, dependent)` pairs — reads as "dependency feeds dependent".
    edges: list[tuple[str, str]] = field(default_factory=list)
    #: Every feature name, ordered so each name appears after everything it
    #: depends on — the order a consumer would need to compute them in, if
    #: `generate()` ever gained the ability to receive another feature's
    #: already-computed columns as input (see `FeatureMetadata.dependencies`'
    #: own docstring for why that doesn't exist yet).
    topological_order: list[str] = field(default_factory=list)


def build_lineage_graph(registry: FeatureRegistry) -> FeatureLineageGraph:
    """Resolve the full lineage graph for every generator in `registry`."""
    names = registry.names()
    direct_dependencies = {name: registry.get(name).metadata.dependencies for name in names}

    depended_on_by: dict[str, list[str]] = {name: [] for name in names}
    edges: list[tuple[str, str]] = []
    for name in names:
        for dependency in direct_dependencies[name]:
            depended_on_by[dependency].append(name)
            edges.append((dependency, name))

    ancestors = {name: _transitive_closure(name, direct_dependencies) for name in names}
    descendants = {name: _transitive_closure(name, depended_on_by) for name in names}
    order = _topological_order(names, direct_dependencies)

    nodes = [
        FeatureLineageNode(
            name=name,
            label=registry.get(name).metadata.label,
            category=registry.get(name).metadata.category,
            dependencies=tuple(direct_dependencies[name]),
            depended_on_by=tuple(sorted(depended_on_by[name])),
            ancestors=tuple(sorted(ancestors[name])),
            descendants=tuple(sorted(descendants[name])),
        )
        for name in names
    ]
    return FeatureLineageGraph(nodes=nodes, edges=edges, topological_order=order)


def _transitive_closure(
    name: str, edges: dict[str, list[str]] | dict[str, tuple[str, ...]]
) -> set[str]:
    """Every node reachable from `name` by following `edges`, excluding `name` itself."""
    visited: set[str] = set()
    stack = list(edges.get(name, ()))
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        stack.extend(edges.get(current, ()))
    return visited


def _topological_order(
    names: tuple[str, ...], direct_dependencies: dict[str, tuple[str, ...]]
) -> list[str]:
    """Depth-first topological sort — each name after everything it depends on.

    Mirrors `FeatureRegistry._check_cycle`'s own visiting/resolved DFS shape
    (same three-color traversal), reused conceptually rather than by
    import: that method is registry-internal and raises as a side effect of
    *validation*; this one's job is to *produce an order*, assuming the
    graph the registry already validated is acyclic. Still raises the same
    `FeatureDependencyCycleError` in the defensive case described in this
    module's own docstring.
    """
    visiting: set[str] = set()
    resolved: set[str] = set()
    order: list[str] = []

    def visit(name: str, path: list[str]) -> None:
        if name in resolved:
            return
        if name in visiting:
            cycle_start = path.index(name)
            raise FeatureDependencyCycleError(tuple((*path[cycle_start:], name)))
        visiting.add(name)
        for dependency in direct_dependencies.get(name, ()):
            visit(dependency, [*path, name])
        visiting.discard(name)
        resolved.add(name)
        order.append(name)

    for name in names:
        visit(name, [])
    return order
