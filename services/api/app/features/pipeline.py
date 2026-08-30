"""The feature generation pipeline.

One fixed sequence of stages, applied identically to every generator:

    resolve → validate parameters → check warmup → generate
            → verify alignment → verify column uniqueness

Every stage is generator-agnostic. The pipeline has no branch on which
generator it is running and imports no concrete generator — that is what
makes the "add a feature without modifying the pipeline core" guarantee
structural rather than a convention someone has to remember.

A whole-dataset result cache deliberately does **not** live here: a feature
request is a *dataset* request, its output is proportional to the whole
candle range rather than a single number, and the expensive part (loading
candles) happens once per dataset upstream — caching whole datasets
in-process would trade a large amount of memory for a saving the batched
candle load already captures. What *does* live here, at the same
per-generator granularity ``IndicatorEngine`` already caches at, is an
optional ``FeatureCache`` (``app/features/cache.py``): one entry per
(feature, params, candle-range) triple, not per dataset. Indicator-backed
generators (``sma``/``ema``/``wma``) already get this for free from the
shared ``IndicatorEngine`` cache underneath; this is what extends the same
benefit to ``ohlcv``/``candle_shape`` and any future non-indicator-backed
generator.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.features.base import (
    FeatureContext,
    FeatureGenerator,
    FeatureMetadata,
    FeatureOutput,
    OHLCVPoint,
)
from app.features.cache import FeatureCache, FeatureCacheKey, build_feature_cache_key
from app.features.errors import (
    FeatureExecutionError,
    InsufficientFeatureDataError,
    InvalidFeatureParameterError,
)
from app.features.registry import FeatureRegistry
from app.indicators.errors import InvalidIndicatorParameterError
from app.indicators.params import validate_parameters

logger = logging.getLogger("app.features.pipeline")

#: The pipeline's own version, independent of any generator's
#: ``FeatureMetadata.version`` — bump it when the *pipeline* changes in a
#: way that could affect any generator's output. Recorded on every dataset
#: so a stored dataset names the exact machinery that produced it, which is
#: the reproducibility guarantee D6/D7 require.
PIPELINE_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class FeatureRun:
    """The result of generating one feature, plus how it was produced."""

    metadata: FeatureMetadata
    params: dict[str, Any]
    output: FeatureOutput
    warmup: int
    execution_time_ms: float
    #: ``"hit"``, ``"miss"``, or ``"disabled"`` — mirrors ``IndicatorRun``'s
    #: own field of the same name and meaning.
    cache_status: str = "disabled"


class FeaturePipeline:
    """Runs registered feature generators through a single, uniform pipeline."""

    def __init__(self, registry: FeatureRegistry, cache: FeatureCache | None = None) -> None:
        self._registry = registry
        self._cache = cache

    @property
    def registry(self) -> FeatureRegistry:
        """The registry this pipeline resolves generators from."""
        return self._registry

    def describe_all(self) -> list[FeatureMetadata]:
        """Metadata for every registered generator (the catalogue)."""
        return self._registry.describe_all()

    def describe(self, name: str) -> FeatureMetadata:
        """Metadata for one generator, or raise ``FeatureNotFoundError``."""
        return self._registry.get(name).metadata

    def warmup_for(self, name: str, raw_params: Mapping[str, Any] | None = None) -> int:
        """Warmup one generator needs for these parameters, without running it.

        The dataset builder needs this *before* generating anything, to
        size the candle window it has to load so that the requested rows
        survive warmup trimming.
        """
        generator = self._registry.get(name)
        params = self._validate(generator, raw_params or {})
        return self._warmup(generator, params)

    def run(
        self,
        name: str,
        candles: Sequence[OHLCVPoint],
        raw_params: Mapping[str, Any] | None = None,
    ) -> FeatureRun:
        """Generate one feature's columns over ``candles``.

        ``raw_params`` may hold un-coerced values (strings from a query or
        JSON layer); they are validated against the generator's own specs
        before anything is computed.
        """
        started = perf_counter()
        generator = self._registry.get(name)
        metadata = generator.metadata

        params = self._validate(generator, raw_params or {})
        warmup = self._warmup(generator, params)
        # Checked here, before generation, so an under-sized range is an
        # actionable 400 naming the shortfall rather than whatever the
        # generator happens to do about it — a delegating generator would
        # otherwise let its own engine's error escape through the generic
        # failure boundary below and surface as an opaque 500.
        if len(candles) < warmup:
            raise InsufficientFeatureDataError(name, warmup, len(candles))

        cached, key = self._lookup(name, params, candles)
        if cached is not None:
            return FeatureRun(
                metadata=metadata,
                params=params,
                output=cached,
                warmup=warmup,
                cache_status="hit",
                execution_time_ms=(perf_counter() - started) * 1000,
            )

        output = self._generate(generator, FeatureContext(candles=candles, params=params))
        self._verify_alignment(name, output, len(candles))
        self._verify_unique_columns(name, output)

        if self._cache is not None and key is not None:
            self._cache.put(key, output)

        elapsed_ms = (perf_counter() - started) * 1000
        logger.debug(
            "Generated feature (name=%s candles=%d columns=%d took=%.2fms)",
            name,
            len(candles),
            len(output.series),
            elapsed_ms,
        )
        return FeatureRun(
            metadata=metadata,
            params=params,
            output=output,
            warmup=warmup,
            cache_status="miss" if self._cache is not None else "disabled",
            execution_time_ms=elapsed_ms,
        )

    def _lookup(
        self,
        name: str,
        params: Mapping[str, Any],
        candles: Sequence[OHLCVPoint],
    ) -> tuple[FeatureOutput | None, FeatureCacheKey | None]:
        """Check the cache, returning the hit (if any) and the key to store under."""
        if self._cache is None:
            return None, None
        key = build_feature_cache_key(name, params, candles)
        return self._cache.get(key), key

    def _validate(
        self, generator: FeatureGenerator, raw_params: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Validate against the generator's specs, re-labelling the error for this context.

        ``validate_parameters`` is reused wholesale from the indicator
        engine — a parameter is a parameter, and a second copy of bounds/
        choices/coercion logic would inevitably drift. Only the raised
        error type is translated, so a caller sees
        ``invalid_feature_parameter`` (naming the feature that rejected it)
        rather than an ``invalid_indicator_parameter`` mentioning an
        indicator the caller never asked for.
        """
        name = generator.metadata.name
        try:
            return validate_parameters(generator.metadata.parameters, raw_params)
        except InvalidIndicatorParameterError as exc:
            raise InvalidFeatureParameterError(name, exc.message) from exc

    def _warmup(self, generator: FeatureGenerator, params: Mapping[str, Any]) -> int:
        """Ask the generator for its warmup, treating a failure as its own bug."""
        try:
            return max(0, int(generator.warmup(params)))
        except Exception as exc:  # noqa: BLE001 - surfaced as a named domain error
            raise FeatureExecutionError(
                generator.metadata.name, f"warmup() raised {type(exc).__name__}: {exc}"
            ) from exc

    def _generate(self, generator: FeatureGenerator, ctx: FeatureContext) -> FeatureOutput:
        """Run the generator, converting any unexpected failure into a named error.

        A bug in one generator must not surface as an anonymous 500 for a
        whole dataset request — ``FeatureExecutionError`` names the culprit
        so the offending implementation is obvious from the response alone.
        """
        name = generator.metadata.name
        try:
            return generator.generate(ctx)
        except Exception as exc:  # noqa: BLE001 - deliberate boundary around generator code
            logger.exception("Feature %r raised during generation", name)
            raise FeatureExecutionError(name, f"{type(exc).__name__}: {exc}") from exc

    def _verify_alignment(self, name: str, output: FeatureOutput, expected: int) -> None:
        """Enforce the one contract a generator can silently break.

        Columns must be aligned index-for-index with the input candles. A
        misaligned column would still serialize, still export, and still
        train a model — just against the wrong timestamps, which is exactly
        the kind of wrong-but-plausible output a research platform must
        never produce. Checking it centrally means every generator gets the
        guarantee for free.
        """
        if not output.series:
            raise FeatureExecutionError(name, "returned no output columns")
        for series in output.series:
            if len(series.values) != expected:
                raise FeatureExecutionError(
                    name,
                    f"column {series.column.name!r} returned {len(series.values)} values "
                    f"for {expected} candles; output must align with the input",
                )

    def _verify_unique_columns(self, name: str, output: FeatureOutput) -> None:
        """Reject a generator that returns the same column name twice.

        Cross-generator collisions are the dataset builder's job (it is the
        only component that sees more than one generator); this catches the
        within-one-generator case at its source.
        """
        seen: set[str] = set()
        for series in output.series:
            column = series.column.name
            if column in seen:
                raise FeatureExecutionError(name, f"returned column {column!r} more than once")
            seen.add(column)
