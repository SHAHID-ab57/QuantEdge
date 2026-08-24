"""The indicator execution pipeline.

One fixed sequence of stages, applied identically to every indicator:

    resolve → validate parameters → check warmup → cache lookup
            → calculate → verify alignment → cache store

Every stage is indicator-agnostic. The engine has no branch on which
indicator it is running and imports no concrete indicator — that is what
makes the "add an indicator without modifying the engine core" guarantee
structural rather than a convention someone has to remember.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.indicators.base import (
    Indicator,
    IndicatorContext,
    IndicatorMetadata,
    IndicatorOutput,
    OHLCVPoint,
)
from app.indicators.cache import IndicatorCache, build_cache_key
from app.indicators.errors import (
    IndicatorExecutionError,
    InsufficientDataError,
)
from app.indicators.params import validate_parameters
from app.indicators.registry import IndicatorRegistry

logger = logging.getLogger("app.indicators.engine")


@dataclass(frozen=True, slots=True)
class IndicatorRun:
    """The result of one execution, plus how it was produced."""

    metadata: IndicatorMetadata
    params: dict[str, Any]
    output: IndicatorOutput
    warmup: int
    #: ``"hit"``, ``"miss"``, or ``"disabled"`` — mirrors the ``cache_status``
    #: field the market-data API's ``QueryMetadata`` already reports.
    cache_status: str
    execution_time_ms: float


class IndicatorEngine:
    """Runs registered indicators through a single, uniform pipeline."""

    def __init__(
        self,
        registry: IndicatorRegistry,
        cache: IndicatorCache | None = None,
    ) -> None:
        self._registry = registry
        self._cache = cache

    @property
    def registry(self) -> IndicatorRegistry:
        """The registry this engine resolves indicators from."""
        return self._registry

    def describe_all(self) -> list[IndicatorMetadata]:
        """Metadata for every registered indicator (the catalogue)."""
        return self._registry.describe_all()

    def describe(self, name: str) -> IndicatorMetadata:
        """Metadata for one indicator, or raise ``IndicatorNotFoundError``."""
        return self._registry.get(name).metadata

    def run(
        self,
        name: str,
        candles: Sequence[OHLCVPoint],
        raw_params: Mapping[str, Any] | None = None,
    ) -> IndicatorRun:
        """Execute one indicator over ``candles``.

        ``raw_params`` may hold un-coerced values (strings from a query
        layer); they are validated against the indicator's own specs before
        anything is computed.
        """
        started = perf_counter()
        indicator = self._registry.get(name)
        metadata = indicator.metadata

        params = validate_parameters(metadata.parameters, raw_params or {})
        warmup = self._warmup(indicator, params)
        if len(candles) < warmup:
            raise InsufficientDataError(name, warmup, len(candles))

        cached, key = self._lookup(name, params, candles)
        if cached is not None:
            return IndicatorRun(
                metadata=metadata,
                params=params,
                output=cached,
                warmup=warmup,
                cache_status="hit",
                execution_time_ms=(perf_counter() - started) * 1000,
            )

        output = self._calculate(indicator, IndicatorContext(candles=candles, params=params))
        self._verify_alignment(name, output, len(candles))

        if self._cache is not None and key is not None:
            self._cache.put(key, output)

        elapsed_ms = (perf_counter() - started) * 1000
        logger.info(
            "Calculated indicator (name=%s candles=%d warmup=%d series=%d took=%.2fms)",
            name,
            len(candles),
            warmup,
            len(output.series),
            elapsed_ms,
        )
        return IndicatorRun(
            metadata=metadata,
            params=params,
            output=output,
            warmup=warmup,
            cache_status="miss" if self._cache is not None else "disabled",
            execution_time_ms=elapsed_ms,
        )

    def _warmup(self, indicator: Indicator, params: Mapping[str, Any]) -> int:
        """Ask the indicator for its warmup, treating a failure as its own bug."""
        try:
            return max(0, int(indicator.warmup(params)))
        except Exception as exc:  # noqa: BLE001 - surfaced as a named domain error
            raise IndicatorExecutionError(
                indicator.metadata.name, f"warmup() raised {type(exc).__name__}: {exc}"
            ) from exc

    def _lookup(
        self,
        name: str,
        params: Mapping[str, Any],
        candles: Sequence[OHLCVPoint],
    ) -> tuple[IndicatorOutput | None, object | None]:
        """Check the cache, returning the hit (if any) and the key to store under."""
        if self._cache is None:
            return None, None
        key = build_cache_key(name, params, candles)
        return self._cache.get(key), key

    def _calculate(self, indicator: Indicator, ctx: IndicatorContext) -> IndicatorOutput:
        """Run the indicator, converting any unexpected failure into a named error.

        A bug in one indicator must not surface as an anonymous 500 for the
        whole API — ``IndicatorExecutionError`` names the culprit so the
        offending implementation is obvious from the response alone.
        """
        try:
            return indicator.calculate(ctx)
        except Exception as exc:  # noqa: BLE001 - deliberate boundary around third-party code
            logger.exception("Indicator %r raised during calculation", indicator.metadata.name)
            raise IndicatorExecutionError(
                indicator.metadata.name, f"{type(exc).__name__}: {exc}"
            ) from exc

    def _verify_alignment(self, name: str, output: IndicatorOutput, expected: int) -> None:
        """Enforce the one contract an indicator can silently break.

        Series must be aligned index-for-index with the input candles (see
        ``IndicatorSeries``). A misaligned series would still serialize
        fine and would still plot — just against the wrong timestamps,
        which is precisely the kind of wrong-but-plausible output a
        research tool must never produce. Checking it here means every
        indicator gets the guarantee for free.
        """
        if not output.series:
            raise IndicatorExecutionError(name, "returned no output series")
        for series in output.series:
            if len(series.values) != expected:
                raise IndicatorExecutionError(
                    name,
                    f"series {series.name!r} returned {len(series.values)} values "
                    f"for {expected} candles; output must align with the input",
                )
