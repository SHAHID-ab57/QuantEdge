"""The target registry — the ML Dataset Builder's extension point.

Same shape as `FeatureRegistry`/`IndicatorRegistry`/`ValidationRuleRegistry`
for the same reason: a new target is a subclass decorated with `@register`
and nothing else changes. A separate registry from `FeatureRegistry` — not
an optional "kind" flag on a shared one — is deliberate: see
`app/ml_datasets/base.py`'s module docstring for why keeping targets and
features in disjoint namespaces is itself a leakage-prevention mechanism.
"""

import logging
from collections.abc import Iterator

from app.ml_datasets.base import TargetGenerator, TargetMetadata
from app.ml_datasets.errors import DuplicateTargetError, TargetNotFoundError

logger = logging.getLogger("app.ml_datasets.registry")


class TargetRegistry:
    """A name → target-generator-instance mapping.

    Generators are instantiated once at registration and reused: they are
    required to be stateless (all state arrives via `TargetContext`), so one
    instance can serve every concurrent request without locking.
    """

    def __init__(self) -> None:
        self._generators: dict[str, TargetGenerator] = {}

    def register(self, generator_cls: type[TargetGenerator]) -> type[TargetGenerator]:
        """Register a target generator class. Usable directly as a decorator."""
        metadata = getattr(generator_cls, "metadata", None)
        if metadata is None:
            raise TypeError(
                f"{generator_cls.__name__} must declare a class-level "
                "`metadata: TargetMetadata` to be registered"
            )
        name = metadata.name
        if name in self._generators:
            raise DuplicateTargetError(name)
        self._generators[name] = generator_cls()
        logger.debug("Registered target %r (%s)", name, generator_cls.__name__)
        return generator_cls

    def get(self, name: str) -> TargetGenerator:
        """Resolve a target generator by name, or raise a 404 domain error."""
        generator = self._generators.get(name)
        if generator is None:
            raise TargetNotFoundError(name, self.names())
        return generator

    def has(self, name: str) -> bool:
        """Whether a target generator with this name is registered."""
        return name in self._generators

    def names(self) -> tuple[str, ...]:
        """Every registered name, sorted for a stable catalogue order."""
        return tuple(sorted(self._generators))

    def describe_all(self) -> list[TargetMetadata]:
        """Metadata for every registered target generator, sorted by name."""
        return [self._generators[name].metadata for name in self.names()]

    def __len__(self) -> int:
        return len(self._generators)

    def __iter__(self) -> Iterator[TargetGenerator]:
        return (self._generators[name] for name in self.names())


#: The registry the application uses. Builtin targets register into this
#: one at import time; `get_target_pipeline` serves it to the API.
default_registry = TargetRegistry()


def register(generator_cls: type[TargetGenerator]) -> type[TargetGenerator]:
    """Register a target generator class into the application's default registry."""
    return default_registry.register(generator_cls)
