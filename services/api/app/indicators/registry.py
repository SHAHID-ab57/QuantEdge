"""The indicator registry — the platform's single extension point.

The engine never imports a concrete indicator. It asks the registry for one
by name, which is what makes "add an indicator without modifying the engine
core" true rather than aspirational: a new indicator is a new module that
registers itself, and nothing else changes.

Registration is by decorator at class-definition time, so importing a
module is what makes its indicator available (the same mechanism pytest
plugins and Django apps use). ``app.indicators.builtin`` turns that into
zero-touch discovery — see ``load_builtin_indicators``.
"""

import logging
from collections.abc import Iterator

from app.indicators.base import Indicator, IndicatorMetadata
from app.indicators.errors import DuplicateIndicatorError, IndicatorNotFoundError

logger = logging.getLogger("app.indicators.registry")


class IndicatorRegistry:
    """A name → indicator-instance mapping.

    Indicators are instantiated once at registration and reused: they are
    required to be stateless (all state arrives via ``IndicatorContext``),
    so one instance can serve every concurrent request without locking.

    Instantiable rather than a module-level singleton so tests — and any
    future caller that needs a restricted catalogue, such as a backtest
    pinned to a fixed indicator set — can build an isolated registry.
    """

    def __init__(self) -> None:
        self._indicators: dict[str, Indicator] = {}

    def register(self, indicator_cls: type[Indicator]) -> type[Indicator]:
        """Register an indicator class. Usable directly as a decorator.

        Returns the class unchanged so stacking or subclassing still works.
        """
        metadata = getattr(indicator_cls, "metadata", None)
        if metadata is None:
            raise TypeError(
                f"{indicator_cls.__name__} must declare a class-level "
                "`metadata: IndicatorMetadata` to be registered"
            )
        name = metadata.name
        if name in self._indicators:
            raise DuplicateIndicatorError(name)
        self._indicators[name] = indicator_cls()
        logger.debug("Registered indicator %r (%s)", name, indicator_cls.__name__)
        return indicator_cls

    def get(self, name: str) -> Indicator:
        """Resolve an indicator by name, or raise a 404 domain error."""
        indicator = self._indicators.get(name)
        if indicator is None:
            raise IndicatorNotFoundError(name, self.names())
        return indicator

    def has(self, name: str) -> bool:
        """Whether an indicator with this name is registered."""
        return name in self._indicators

    def names(self) -> tuple[str, ...]:
        """Every registered name, sorted for a stable catalogue order."""
        return tuple(sorted(self._indicators))

    def describe_all(self) -> list[IndicatorMetadata]:
        """Metadata for every registered indicator, sorted by name."""
        return [self._indicators[name].metadata for name in self.names()]

    def __len__(self) -> int:
        return len(self._indicators)

    def __iter__(self) -> Iterator[Indicator]:
        return (self._indicators[name] for name in self.names())


#: The registry the application uses. Builtin indicators register into this
#: one at import time; ``get_indicator_engine`` serves it to the API.
default_registry = IndicatorRegistry()


def register(indicator_cls: type[Indicator]) -> type[Indicator]:
    """Register an indicator into the application's default registry.

    The decorator every builtin indicator uses::

        @register
        class SimpleMovingAverage(Indicator):
            metadata = IndicatorMetadata(name="sma", ...)
    """
    return default_registry.register(indicator_cls)
