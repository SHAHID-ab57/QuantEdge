"""The metric registry — the Evaluation Engine's extension point.

Same shape as `app/training/registry.py`'s `ModelAdapterRegistry` (and
`TargetRegistry`/`FeatureRegistry`/`ValidationRuleRegistry` before it): a new
metric is a subclass decorated with `@register` and nothing else in this
package, the engine, the service layer, or the API changes.
"""

import logging
from collections.abc import Iterator

from app.evaluation.base import Metric, MetricCategory, MetricMetadata
from app.evaluation.errors import DuplicateMetricError, MetricNotFoundError

logger = logging.getLogger("app.evaluation.registry")


class MetricRegistry:
    """A name -> metric-instance mapping.

    Metrics are instantiated once at registration and reused, mirroring
    `ModelAdapterRegistry`'s own statelessness requirement: all per-call state
    (predictions, probabilities) arrives via `compute`'s own arguments, never
    stored on the instance.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, Metric] = {}

    def register(self, metric_cls: type[Metric]) -> type[Metric]:
        """Register a metric class. Usable directly as a decorator."""
        metadata = getattr(metric_cls, "metadata", None)
        if metadata is None:
            raise TypeError(
                f"{metric_cls.__name__} must declare a class-level "
                "`metadata: MetricMetadata` to be registered"
            )
        name = metadata.name
        if name in self._metrics:
            raise DuplicateMetricError(name)
        self._metrics[name] = metric_cls()
        logger.debug("Registered metric %r (%s)", name, metric_cls.__name__)
        return metric_cls

    def get(self, name: str) -> Metric:
        """Resolve a metric by name, or raise a 404 domain error."""
        metric = self._metrics.get(name)
        if metric is None:
            raise MetricNotFoundError(name, self.names())
        return metric

    def has(self, name: str) -> bool:
        """Whether a metric with this name is registered."""
        return name in self._metrics

    def names(self) -> tuple[str, ...]:
        """Every registered name, sorted for a stable catalogue order."""
        return tuple(sorted(self._metrics))

    def describe_all(self) -> list[MetricMetadata]:
        """Metadata for every registered metric, sorted by name."""
        return [self._metrics[name].metadata for name in self.names()]

    def for_category(self, category: MetricCategory) -> list[Metric]:
        """Every registered metric applicable to `category`, sorted by name."""
        return [
            self._metrics[name]
            for name in self.names()
            if self._metrics[name].metadata.category == category
        ]

    def __len__(self) -> int:
        return len(self._metrics)

    def __iter__(self) -> Iterator[Metric]:
        return (self._metrics[name] for name in self.names())


#: The registry the application uses. Builtin metrics register into this one
#: at import time; `get_evaluation_engine` serves it to the API.
default_registry = MetricRegistry()


def register(metric_cls: type[Metric]) -> type[Metric]:
    """Register a metric class into the application's default registry."""
    return default_registry.register(metric_cls)
