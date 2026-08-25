"""The feature registry — the Feature Engineering context's extension point.

The pipeline never imports a concrete generator. It asks the registry for
one by name, which is what makes "add a feature without modifying the
engine core" true rather than aspirational.

Two registration styles are supported, and the difference matters:

- ``@register`` over a class, for a generator written by hand — the same
  decorator-at-class-definition-time mechanism ``app/indicators/`` uses.
- ``register_generator(instance)`` for a generator *constructed* rather
  than declared. This exists for adapters: ``IndicatorFeature`` wraps an
  already-registered indicator, so the SMA/EMA/WMA features are built by
  instantiating one adapter class three times rather than by writing three
  near-identical subclasses. Without instance registration, reusing the
  indicator engine would have meant duplicating its metadata into a
  hand-written subclass per indicator — precisely the duplication the
  adapter exists to avoid.
"""

import logging
from collections.abc import Iterator

from app.features.base import FeatureGenerator, FeatureMetadata
from app.features.errors import (
    DuplicateFeatureError,
    FeatureDependencyCycleError,
    FeatureNotFoundError,
    UnknownFeatureDependencyError,
)

logger = logging.getLogger("app.features.registry")


class FeatureRegistry:
    """A name → generator-instance mapping.

    Generators are instantiated once at registration and reused: they are
    required to be stateless (all state arrives via ``FeatureContext``), so
    one instance can serve every concurrent request without locking.

    Instantiable rather than a module-level singleton so tests — and any
    future caller that needs a restricted catalogue, such as a training run
    pinned to an exact feature set for reproducibility — can build an
    isolated registry.
    """

    def __init__(self) -> None:
        self._generators: dict[str, FeatureGenerator] = {}

    def register(self, generator_cls: type[FeatureGenerator]) -> type[FeatureGenerator]:
        """Register a generator class. Usable directly as a decorator.

        Returns the class unchanged so stacking or subclassing still works.
        """
        metadata = getattr(generator_cls, "metadata", None)
        if metadata is None:
            raise TypeError(
                f"{generator_cls.__name__} must declare a class-level "
                "`metadata: FeatureMetadata` to be registered"
            )
        self.register_generator(generator_cls())
        return generator_cls

    def register_generator(self, generator: FeatureGenerator) -> FeatureGenerator:
        """Register an already-constructed generator instance.

        Returns it unchanged, so a caller can keep a reference to what it
        registered.
        """
        metadata = getattr(generator, "metadata", None)
        if metadata is None:
            raise TypeError(
                f"{type(generator).__name__} must declare `metadata: FeatureMetadata` "
                "to be registered"
            )
        name = metadata.name
        if name in self._generators:
            raise DuplicateFeatureError(name)
        self._generators[name] = generator
        logger.debug("Registered feature %r (%s)", name, type(generator).__name__)
        return generator

    def get(self, name: str) -> FeatureGenerator:
        """Resolve a generator by name, or raise a 404 domain error."""
        generator = self._generators.get(name)
        if generator is None:
            raise FeatureNotFoundError(name, self.names())
        return generator

    def has(self, name: str) -> bool:
        """Whether a generator with this name is registered."""
        return name in self._generators

    def names(self) -> tuple[str, ...]:
        """Every registered name, sorted for a stable catalogue order."""
        return tuple(sorted(self._generators))

    def describe_all(self) -> list[FeatureMetadata]:
        """Metadata for every registered generator, sorted by name."""
        return [self._generators[name].metadata for name in self.names()]

    def validate_dependencies(self) -> None:
        """Check every registered generator's declared dependency graph.

        Two structural checks, run once (typically at startup, from
        ``load_builtin_features``): every name in every generator's
        ``metadata.dependencies`` must itself be a registered feature
        (``UnknownFeatureDependencyError``), and the graph they form must
        contain no cycle (``FeatureDependencyCycleError``) — a cycle would
        make "the features this dataset needs" unresolvable in any order.
        Both are developer mistakes in a generator's own declaration, so
        both raise a plain ``RuntimeError`` subclass rather than an
        ``AppError``: no HTTP request can cause either, and failing fast at
        startup is strictly better than a request-time surprise.
        """
        for name in self.names():
            dependencies = self._generators[name].metadata.dependencies
            unknown = tuple(dep for dep in dependencies if not self.has(dep))
            if unknown:
                raise UnknownFeatureDependencyError(name, unknown)

        visiting: set[str] = set()
        resolved: set[str] = set()
        for name in self.names():
            self._check_cycle(name, visiting, resolved, path=[])

    def _check_cycle(
        self, name: str, visiting: set[str], resolved: set[str], path: list[str]
    ) -> None:
        """Depth-first cycle detection over the dependency graph."""
        if name in resolved:
            return
        if name in visiting:
            cycle_start = path.index(name)
            raise FeatureDependencyCycleError(tuple((*path[cycle_start:], name)))
        visiting.add(name)
        for dependency in self._generators[name].metadata.dependencies:
            self._check_cycle(dependency, visiting, resolved, [*path, name])
        visiting.discard(name)
        resolved.add(name)

    def __len__(self) -> int:
        return len(self._generators)

    def __iter__(self) -> Iterator[FeatureGenerator]:
        return (self._generators[name] for name in self.names())


#: The registry the application uses. Builtin generators register into this
#: one at import time; ``get_feature_pipeline`` serves it to the API.
default_registry = FeatureRegistry()


def register(generator_cls: type[FeatureGenerator]) -> type[FeatureGenerator]:
    """Register a generator class into the application's default registry."""
    return default_registry.register(generator_cls)


def register_generator(generator: FeatureGenerator) -> FeatureGenerator:
    """Register a constructed generator instance into the default registry."""
    return default_registry.register_generator(generator)
