"""The target generation pipeline.

One fixed sequence of stages, mirroring `FeaturePipeline` exactly but
looking the opposite direction in time:

    resolve → validate parameters → check horizon → generate
            → verify alignment → verify the forward-looking contract
            → verify column uniqueness

Where a feature's pipeline checks *warmup* (candles needed before the
first defined value, at the *start* of a column), this pipeline checks
*horizon* (candles needed after the last defined value, at the *end* of a
column) — the mirror image, not a coincidence: a target is a label that
looks into the future relative to the row it's attached to, so it runs out
of information at the opposite end of the series from a feature.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.indicators.errors import InvalidIndicatorParameterError
from app.indicators.params import validate_parameters
from app.ml_datasets.base import (
    OHLCVPoint,
    TargetContext,
    TargetGenerator,
    TargetMetadata,
    TargetOutput,
)
from app.ml_datasets.errors import (
    InsufficientTargetDataError,
    InvalidTargetParameterError,
    TargetAlignmentError,
    TargetExecutionError,
)
from app.ml_datasets.registry import TargetRegistry

logger = logging.getLogger("app.ml_datasets.pipeline")

#: The pipeline's own version, independent of any target's own
#: `TargetMetadata.version` — bump it when the *pipeline* changes in a way
#: that could affect any target's output. Mirrors
#: `app.features.pipeline.PIPELINE_VERSION`.
TARGET_PIPELINE_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class TargetRun:
    """The result of generating one target, plus how it was produced."""

    metadata: TargetMetadata
    params: dict[str, Any]
    output: TargetOutput
    horizon: int
    execution_time_ms: float


class TargetPipeline:
    """Runs registered target generators through a single, uniform pipeline."""

    def __init__(self, registry: TargetRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> TargetRegistry:
        """The registry this pipeline resolves generators from."""
        return self._registry

    def describe_all(self) -> list[TargetMetadata]:
        """Metadata for every registered target generator (the catalogue)."""
        return self._registry.describe_all()

    def describe(self, name: str) -> TargetMetadata:
        """Metadata for one target generator, or raise `TargetNotFoundError`."""
        return self._registry.get(name).metadata

    def horizon_for(self, name: str, raw_params: Mapping[str, Any] | None = None) -> int:
        """Horizon one target needs for these parameters, without running it.

        The dataset builder needs this *before* trimming trailing rows, to
        know how many rows at the end of the series can never have a
        defined value for this target.
        """
        generator = self._registry.get(name)
        params = self._validate(generator, raw_params or {})
        return self._horizon(generator, params)

    def run(
        self,
        name: str,
        candles: Sequence[OHLCVPoint],
        raw_params: Mapping[str, Any] | None = None,
    ) -> TargetRun:
        """Generate one target's columns over `candles`."""
        started = perf_counter()
        generator = self._registry.get(name)
        metadata = generator.metadata

        params = self._validate(generator, raw_params or {})
        horizon = self._horizon(generator, params)
        # A target needs one candle to predict *from*, plus `horizon`
        # candles past it to know the answer — checked here, before
        # generation, for the same reason a feature's warmup is checked
        # before generation: an actionable 400 naming the shortfall, not
        # whatever the generator happens to do with too little data.
        if len(candles) < horizon + 1:
            raise InsufficientTargetDataError(name, horizon, len(candles))

        output = self._generate(generator, TargetContext(candles=candles, params=params))
        self._verify_alignment(name, output, len(candles))
        self._verify_forward_looking_contract(name, output, len(candles), horizon)
        self._verify_unique_columns(name, output)

        elapsed_ms = (perf_counter() - started) * 1000
        logger.debug(
            "Generated target (name=%s candles=%d columns=%d horizon=%d took=%.2fms)",
            name,
            len(candles),
            len(output.series),
            horizon,
            elapsed_ms,
        )
        return TargetRun(
            metadata=metadata,
            params=params,
            output=output,
            horizon=horizon,
            execution_time_ms=elapsed_ms,
        )

    def _validate(
        self, generator: TargetGenerator, raw_params: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Validate against the generator's specs, re-labelling the error for this context."""
        name = generator.metadata.name
        try:
            return validate_parameters(generator.metadata.parameters, raw_params)
        except InvalidIndicatorParameterError as exc:
            raise InvalidTargetParameterError(name, exc.message) from exc

    def _horizon(self, generator: TargetGenerator, params: Mapping[str, Any]) -> int:
        """Ask the generator for its horizon, treating a failure as its own bug."""
        try:
            return max(0, int(generator.horizon(params)))
        except Exception as exc:  # noqa: BLE001 - surfaced as a named domain error
            raise TargetExecutionError(
                generator.metadata.name, f"horizon() raised {type(exc).__name__}: {exc}"
            ) from exc

    def _generate(self, generator: TargetGenerator, ctx: TargetContext) -> TargetOutput:
        """Run the generator, converting any unexpected failure into a named error."""
        name = generator.metadata.name
        try:
            return generator.generate(ctx)
        except Exception as exc:  # noqa: BLE001 - deliberate boundary around generator code
            logger.exception("Target %r raised during generation", name)
            raise TargetExecutionError(name, f"{type(exc).__name__}: {exc}") from exc

    def _verify_alignment(self, name: str, output: TargetOutput, expected: int) -> None:
        """Columns must be aligned index-for-index with the input candles."""
        if not output.series:
            raise TargetExecutionError(name, "returned no output columns")
        for series in output.series:
            if len(series.values) != expected:
                raise TargetExecutionError(
                    name,
                    f"column {series.column.name!r} returned {len(series.values)} values "
                    f"for {expected} candles; output must align with the input",
                )

    def _verify_forward_looking_contract(
        self, name: str, output: TargetOutput, candle_count: int, horizon: int
    ) -> None:
        """Enforce the one contract unique to a *target* generator.

        The last `horizon` positions of every column must be `None` — there
        is no future candle to compute them from, so a generator that
        fills them in anyway is fabricating a value it cannot actually
        know, which is precisely the look-ahead bias this whole engine
        exists to prevent. (A defined value *outside* that trailing window
        is not checked here — a future target with its own lookback
        requirement is free to leave earlier positions `None` too, the
        same way a feature can.)
        """
        if horizon == 0:
            return
        boundary = candle_count - horizon
        for series in output.series:
            trailing = series.values[boundary:]
            if any(value is not None for value in trailing):
                raise TargetAlignmentError(
                    name,
                    f"column {series.column.name!r} has a defined value within its trailing "
                    f"{horizon}-candle horizon window; no future candle exists to compute it "
                    "from",
                )

    def _verify_unique_columns(self, name: str, output: TargetOutput) -> None:
        """Reject a generator that returns the same column name twice."""
        seen: set[str] = set()
        for series in output.series:
            column = series.column.name
            if column in seen:
                raise TargetExecutionError(name, f"returned column {column!r} more than once")
            seen.add(column)
