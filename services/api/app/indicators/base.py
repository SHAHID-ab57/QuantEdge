"""The indicator contract: inputs, outputs, metadata, and the base class.

Nothing in this module imports SQLAlchemy, FastAPI, or Pydantic, and no
indicator implementation should either. An indicator receives plain
``OHLCVPoint`` values and returns plain series — which is what makes the
same implementations reusable from the REST API today and, unchanged, from
a replay session, a backtest, or a feature-engineering job later (see
``ARCHITECTURE.md`` § "Technical Indicator Engine").
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from app.indicators.params import ParameterSpec


@dataclass(frozen=True, slots=True)
class OHLCVPoint:
    """One candle, reduced to the fields indicator math actually needs.

    Prices are ``float`` rather than the database's ``Decimal``: every
    indicator worth the name is an approximation (an EMA has no exact
    decimal representation at all), and carrying 18-digit decimals through
    recursive float math would imply a precision the output does not have.
    The storage layer keeps its exact decimals; this is the analysis view.
    """

    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class IndicatorContext:
    """Everything an indicator is given: the candles and its parameters.

    ``params`` is always complete and already coerced/validated against the
    indicator's own ``ParameterSpec`` list — an implementation never has to
    re-check a bound, supply a default, or parse a string.
    """

    candles: Sequence[OHLCVPoint]
    params: Mapping[str, Any]

    def int_param(self, name: str) -> int:
        """Read a validated ``int`` parameter."""
        return int(self.params[name])

    def float_param(self, name: str) -> float:
        """Read a validated ``float`` parameter."""
        return float(self.params[name])

    def str_param(self, name: str) -> str:
        """Read a validated ``string`` parameter."""
        return str(self.params[name])

    def bool_param(self, name: str) -> bool:
        """Read a validated ``bool`` parameter."""
        return bool(self.params[name])

    def source_values(self, name: str = "source") -> list[float]:
        """Extract the price series named by a ``source`` parameter.

        Shared here rather than reimplemented per indicator, since almost
        every price-based indicator offers the same open/high/low/close
        choice and would otherwise repeat this switch.
        """
        field_name = self.str_param(name)
        return [float(getattr(candle, field_name)) for candle in self.candles]


@dataclass(frozen=True, slots=True)
class SeriesSpec:
    """Declares one output series before the indicator has run.

    Lets the catalogue endpoint (and therefore a UI) describe what an
    indicator will produce without calculating anything.
    """

    name: str
    label: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class IndicatorSeries:
    """One computed output series.

    ``values`` is aligned index-for-index with the input candles, with
    ``None`` for positions inside the warmup period. This alignment is a
    load-bearing part of the contract: it is what lets a caller zip results
    straight onto candle timestamps, and what lets a multi-output indicator
    (MACD, Bollinger Bands) return several series that all line up.
    """

    name: str
    label: str
    values: list[float | None]


@dataclass(frozen=True, slots=True)
class IndicatorOutput:
    """What an indicator returns: one or more aligned series."""

    series: list[IndicatorSeries]


@dataclass(frozen=True, slots=True)
class IndicatorMetadata:
    """Everything the catalogue knows about an indicator without running it."""

    name: str
    label: str
    description: str
    category: str
    parameters: tuple[ParameterSpec, ...] = field(default_factory=tuple)
    outputs: tuple[SeriesSpec, ...] = field(default_factory=tuple)


class Indicator(ABC):
    """Base class for every indicator (the Strategy in Strategy + Registry).

    A new indicator is a subclass that declares ``metadata`` and implements
    ``calculate``; the engine, registry, service, and API need no changes to
    support it. See ``ARCHITECTURE.md`` § "Adding a new indicator" for the
    full workflow.
    """

    metadata: ClassVar[IndicatorMetadata]

    def warmup(self, params: Mapping[str, Any]) -> int:
        """Minimum candles needed before the first non-``None`` value.

        Declared separately from ``calculate`` so the engine can reject an
        under-sized range up front with a specific, actionable error rather
        than returning a series that is entirely ``None``. Defaults to
        ``0`` for indicators that produce a value from the first candle.
        """
        del params
        return 0

    @abstractmethod
    def calculate(self, ctx: IndicatorContext) -> IndicatorOutput:
        """Compute this indicator's series over ``ctx.candles``.

        Implementations may assume parameters are valid and that at least
        ``warmup(params)`` candles are present — the engine enforces both
        before calling.
        """
