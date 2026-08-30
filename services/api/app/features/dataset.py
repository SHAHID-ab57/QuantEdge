"""The feature dataset builder — several features into one aligned matrix.

This is the component that turns "compute these features" into a *dataset*
(``docs/architecture/DataArchitecture.md`` § D7): a rectangular,
row-oriented table with one timestamped row per candle, one column per
requested feature output, and no missing cells.

Three responsibilities that only this component can own, because it is the
only one that sees more than one generator at a time:

1. **Column collision detection.** Two requested features that would
   produce the same column name are rejected, naming both. A silently
   overwritten column is the worst possible dataset defect — the model
   trains on data nobody intended and nothing looks wrong.
2. **Warmup trimming.** Different features warm up over different windows
   (SMA(50) needs 50 candles; ``candle_shape`` needs one). Rows where any
   requested feature is still undefined are dropped by default, because a
   training matrix containing nulls is not usable and silently imputing
   them would be a modelling decision this layer has no business making.
3. **Reproducibility metadata.** Every dataset records the pipeline
   version, the fully-resolved parameters of every feature, and exactly how
   many rows were dropped and why. A dataset that cannot say how it was
   built cannot be reproduced, and an unreproducible dataset is not
   research.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from app.features.base import FeatureColumn, FeatureValue, OHLCVPoint
from app.features.errors import (
    DuplicateFeatureColumnError,
    EmptyDatasetError,
    FeatureExecutionError,
    FeatureNotFoundError,
    InsufficientFeatureDataError,
    InvalidFeatureParameterError,
)
from app.features.pipeline import PIPELINE_VERSION, FeaturePipeline
from app.features.quality import (
    DatasetQualityReport,
    FeatureFailure,
    count_duplicate_timestamps,
    count_missing_candles,
)
from app.features.validation import validate_feature_requests

logger = logging.getLogger("app.features.dataset")

#: Per-request errors that become a recorded `FeatureFailure` rather than
#: aborting the whole build — mirroring `IndicatorService`'s
#: `_BATCH_ITEM_ERRORS` exactly, so the two batch-style endpoints on this
#: platform behave identically: one misconfigured item never blanks out
#: every other correctly-configured one.
_REQUEST_ERRORS = (
    FeatureNotFoundError,
    InvalidFeatureParameterError,
    InsufficientFeatureDataError,
    FeatureExecutionError,
)


@dataclass(frozen=True, slots=True)
class FeatureRequest:
    """One feature to include in a dataset, with its parameters."""

    feature: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DatasetFeatureInfo:
    """How one requested feature actually resolved, for the dataset's record."""

    feature: str
    label: str
    version: str
    #: Fully resolved, defaults applied — the values that actually ran.
    params: dict[str, Any]
    columns: list[str]
    warmup: int
    execution_time_ms: float
    #: ``"hit"``, ``"miss"``, or ``"disabled"`` — see ``FeaturePipeline.run``'s
    #: own ``FeatureRun.cache_status``, which this is copied from verbatim.
    #: Defaulted (rather than required) so existing direct constructions of
    #: this dataclass (e.g. in ``tests/dataset_validation/``, built without
    #: ever running a real pipeline) keep working unchanged.
    cache_status: str = "disabled"


@dataclass(frozen=True, slots=True)
class FeatureDataset:
    """A rectangular, timestamped feature matrix plus its provenance.

    Row-oriented (``rows`` is a list of rows) rather than column-oriented,
    because that is the shape every consumer of a *dataset* wants: a CSV
    writer, a preview table, and a model's training loop all iterate rows.
    The column-oriented shape stays inside the pipeline, where alignment is
    the concern.
    """

    #: Unique per build — a UUID4, not a content hash. This dataset is
    #: identified by *when and how it was requested*, not purely by its
    #: contents: rebuilding the identical request a second time (say, after
    #: new candles have arrived) intentionally yields a new id, since it is
    #: a genuinely different snapshot for reproducibility purposes even if
    #: every value happens to match.
    dataset_id: str
    symbol: str
    timeframe: str
    columns: list[FeatureColumn]
    timestamps: list[datetime]
    rows: list[list[FeatureValue]]
    features: list[DatasetFeatureInfo]
    #: Candles loaded before any warmup trimming.
    candles_analyzed: int
    #: Rows removed because at least one feature was still in warmup.
    rows_dropped: int
    #: The largest warmup across every requested feature — the reason
    #: ``rows_dropped`` is what it is.
    warmup_candles: int
    pipeline_version: str
    generated_at: datetime
    quality: DatasetQualityReport

    @property
    def row_count(self) -> int:
        """Rows in the finished dataset."""
        return len(self.rows)


class FeatureDatasetBuilder:
    """Assembles several generators' output into one aligned dataset."""

    def __init__(self, pipeline: FeaturePipeline) -> None:
        self._pipeline = pipeline

    @property
    def pipeline(self) -> FeaturePipeline:
        """The pipeline this builder runs generators through."""
        return self._pipeline

    def required_warmup(self, requests: list[FeatureRequest]) -> int:
        """The largest warmup across every *resolvable* requested feature.

        Exposed so a caller can widen its candle window *before* loading,
        and get the number of rows it actually asked for rather than that
        number minus the warmup.

        A request that will fail outright (unknown feature name, invalid
        parameter) simply doesn't contribute to the max here — it cannot
        have a meaningful warmup, and its failure is recorded by ``build``
        itself once actually run. Raising here instead would defeat
        ``build``'s own partial-success handling before it ever got a
        chance to run: the whole point is that one bad request among
        several must not prevent the others from being sized and loaded
        correctly.
        """
        warmups: list[int] = []
        for request in requests:
            try:
                warmups.append(self._pipeline.warmup_for(request.feature, request.params))
            except _REQUEST_ERRORS:
                continue
        return max(warmups, default=0)

    def build(
        self,
        symbol: str,
        timeframe: str,
        candles: list[OHLCVPoint],
        requests: list[FeatureRequest],
        *,
        drop_warmup: bool = True,
    ) -> FeatureDataset:
        """Run every requested feature over ``candles`` and assemble the matrix.

        ``drop_warmup`` defaults to ``True`` because the output is a
        *dataset*: a training matrix must not contain nulls, and the
        alternative — leaving them for every downstream consumer to
        rediscover — pushes the same decision onto code far less equipped
        to make it. Nothing is silent about it: ``rows_dropped`` and
        ``warmup_candles`` are reported on every dataset. Set it to
        ``False`` to keep full alignment with the candle range, for
        inspection or for a consumer that imputes its own values.

        One requested feature failing does not abort the others: a bad
        parameter or an under-sized range for *one* feature is recorded as
        a ``FeatureFailure`` on ``quality.feature_failures`` and skipped,
        while every other requested feature still builds — the same
        partial-success contract ``IndicatorService.calculate_batch``
        already established for the indicator batch endpoint, applied here
        for the same reason: one misconfigured item must not blank out
        every correctly-configured one. A structural request problem
        (an unmet dependency, or two features that would collide on the
        same column name) still raises immediately, since there is no
        partial result that would make sense for either.
        """
        validate_feature_requests(self._pipeline, requests)

        columns: list[FeatureColumn] = []
        column_values: list[list[FeatureValue]] = []
        owner_of_column: dict[str, str] = {}
        infos: list[DatasetFeatureInfo] = []
        failures: list[FeatureFailure] = []

        generation_started = perf_counter()
        for request in requests:
            try:
                run = self._pipeline.run(request.feature, candles, request.params)
            except _REQUEST_ERRORS as exc:
                failures.append(
                    FeatureFailure(
                        feature=request.feature,
                        params=dict(request.params),
                        error_code=exc.code,
                        error_detail=exc.message,
                    )
                )
                continue
            produced: list[str] = []
            for series in run.output.series:
                name = series.column.name
                previous = owner_of_column.get(name)
                if previous is not None:
                    raise DuplicateFeatureColumnError(name, previous, request.feature)
                owner_of_column[name] = request.feature
                columns.append(series.column)
                column_values.append(series.values)
                produced.append(name)
            infos.append(
                DatasetFeatureInfo(
                    feature=request.feature,
                    label=run.metadata.label,
                    version=run.metadata.version,
                    params=run.params,
                    columns=produced,
                    warmup=run.warmup,
                    cache_status=run.cache_status,
                    execution_time_ms=run.execution_time_ms,
                )
            )
        generation_time_ms = (perf_counter() - generation_started) * 1000

        warmup = max((info.warmup for info in infos), default=0)
        # No columns means no dataset: a run of empty rows carries no
        # information and would misreport a row count to every consumer.
        row_length = len(candles) if columns else 0
        timestamps = [candle.open_time for candle in candles][:row_length]
        rows = _transpose(column_values, row_length)

        null_counts = _count_nulls(columns, rows)

        kept_timestamps, kept_rows = (
            _drop_incomplete(timestamps, rows) if drop_warmup else (timestamps, rows)
        )
        dropped = len(rows) - len(kept_rows)

        # Only a genuine "every row was warmup" case raises: when every
        # requested feature failed outright, `columns` is empty and the
        # failures are already fully explained by `quality.feature_failures`
        # — that is a valid (if unhelpful) dataset, not an error.
        if drop_warmup and columns and not kept_rows:
            raise EmptyDatasetError(len(candles), warmup)

        all_timestamps = [candle.open_time for candle in candles]
        quality = DatasetQualityReport(
            total_rows=len(candles),
            rows_returned=len(kept_rows),
            rows_removed=dropped,
            null_counts=null_counts,
            duplicate_timestamps=count_duplicate_timestamps(all_timestamps),
            missing_candles=count_missing_candles(all_timestamps, timeframe),
            feature_failures=failures,
            generation_time_ms=generation_time_ms,
        )

        logger.info(
            "Built feature dataset (symbol=%s timeframe=%s features=%d columns=%d "
            "candles=%d rows=%d dropped=%d failures=%d)",
            symbol,
            timeframe,
            len(requests),
            len(columns),
            len(candles),
            len(kept_rows),
            dropped,
            len(failures),
        )
        return FeatureDataset(
            dataset_id=str(uuid.uuid4()),
            symbol=symbol,
            timeframe=timeframe,
            columns=columns,
            timestamps=kept_timestamps,
            rows=kept_rows,
            features=infos,
            candles_analyzed=len(candles),
            rows_dropped=dropped,
            warmup_candles=warmup,
            pipeline_version=PIPELINE_VERSION,
            generated_at=datetime.now(UTC),
            quality=quality,
        )


def _transpose(column_values: list[list[FeatureValue]], length: int) -> list[list[FeatureValue]]:
    """Turn per-column value lists into per-row value lists.

    Every column is already guaranteed by the pipeline to have exactly
    ``length`` values, so this is a plain transpose with no ragged-row
    handling to get wrong.
    """
    return [[column[index] for column in column_values] for index in range(length)]


def _count_nulls(columns: list[FeatureColumn], rows: list[list[FeatureValue]]) -> dict[str, int]:
    """Null count per column, computed *before* warmup trimming.

    Once ``drop_warmup`` removes every incomplete row, every remaining
    column has zero nulls by construction — so this must run on the
    pre-trim rows to say anything the quality report doesn't already know.
    """
    counts = {column.name: 0 for column in columns}
    for row in rows:
        for column, value in zip(columns, row, strict=True):
            if value is None:
                counts[column.name] += 1
    return counts


def _drop_incomplete(
    timestamps: list[datetime], rows: list[list[FeatureValue]]
) -> tuple[list[datetime], list[list[FeatureValue]]]:
    """Drop any row containing a ``None``, keeping timestamps in step.

    Deliberately drops *any* incomplete row rather than only leading warmup
    rows: a null in the middle of a series (a flat candle's undefined
    normalized wick fraction, say) is just as unusable to a model as a
    leading one, and a rule of "complete rows only" is far easier to reason
    about than "leading rows, plus these other cases".
    """
    kept_timestamps: list[datetime] = []
    kept_rows: list[list[FeatureValue]] = []
    for timestamp, row in zip(timestamps, rows, strict=True):
        if any(value is None for value in row):
            continue
        kept_timestamps.append(timestamp)
        kept_rows.append(row)
    return kept_timestamps, kept_rows
