"""The model adapter registry — the Training Framework's extension point.

Same shape as `TargetRegistry`/`FeatureRegistry`/`ValidationRuleRegistry`
for the same reason: a new model adapter is a subclass decorated with
`@register` and nothing else in this package, the service layer, or the API
changes.
"""

import logging
from collections.abc import Iterator

from app.training.base import ModelAdapter, ModelAdapterMetadata
from app.training.errors import DuplicateModelAdapterError, ModelAdapterNotFoundError

logger = logging.getLogger("app.training.registry")


class ModelAdapterRegistry:
    """A name → model-adapter-instance mapping.

    Adapters are instantiated once at registration and reused, mirroring
    `TargetRegistry`'s own statelessness requirement: all per-run state
    arrives via `initialize`/`train` arguments, never stored on the
    instance, so one instance safely serves every concurrent job.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, ModelAdapter] = {}

    def register(self, adapter_cls: type[ModelAdapter]) -> type[ModelAdapter]:
        """Register a model adapter class. Usable directly as a decorator."""
        metadata = getattr(adapter_cls, "metadata", None)
        if metadata is None:
            raise TypeError(
                f"{adapter_cls.__name__} must declare a class-level "
                "`metadata: ModelAdapterMetadata` to be registered"
            )
        name = metadata.name
        if name in self._adapters:
            raise DuplicateModelAdapterError(name)
        self._adapters[name] = adapter_cls()
        logger.debug("Registered model adapter %r (%s)", name, adapter_cls.__name__)
        return adapter_cls

    def get(self, name: str) -> ModelAdapter:
        """Resolve a model adapter by name, or raise a 404 domain error."""
        adapter = self._adapters.get(name)
        if adapter is None:
            raise ModelAdapterNotFoundError(name, self.names())
        return adapter

    def has(self, name: str) -> bool:
        """Whether a model adapter with this name is registered."""
        return name in self._adapters

    def names(self) -> tuple[str, ...]:
        """Every registered name, sorted for a stable catalogue order."""
        return tuple(sorted(self._adapters))

    def describe_all(self) -> list[ModelAdapterMetadata]:
        """Metadata for every registered model adapter, sorted by name."""
        return [self._adapters[name].metadata for name in self.names()]

    def __len__(self) -> int:
        return len(self._adapters)

    def __iter__(self) -> Iterator[ModelAdapter]:
        return (self._adapters[name] for name in self.names())


#: The registry the application uses. Builtin adapters register into this
#: one at import time; `get_training_pipeline` serves it to the API.
default_registry = ModelAdapterRegistry()


def register(adapter_cls: type[ModelAdapter]) -> type[ModelAdapter]:
    """Register a model adapter class into the application's default registry."""
    return default_registry.register(adapter_cls)
