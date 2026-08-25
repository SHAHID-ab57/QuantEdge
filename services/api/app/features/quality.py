"""Data quality reporting for a built dataset.

Answers "can I trust this dataset, and if not, exactly why not" — the
question a researcher asks before training on it. Computed entirely from
data the dataset builder already has in memory (the loaded candle points,
each generator's resolved output, and each request's outcome); nothing here
issues a second database query, unlike the standalone candle-quality report
``app/services/candle_validation.py`` produces for the History page, which
answers a related but different question ("is the *stored* candle data
complete over an arbitrary range") and is deliberately not reused wholesale
here — this report is scoped to exactly the candles one dataset build
already read, at zero extra cost.

``count_missing_candles`` reuses ``resolution_duration`` (the same
timeframe → bucket-length mapping ``candle_validation.py`` and
``candle_ingest.py`` already use) rather than re-declaring a timeframe
table, so "how long is a 1h bucket" has exactly one answer platform-wide.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services.candle_ingest import resolution_duration


@dataclass(frozen=True, slots=True)
class FeatureFailure:
    """One requested feature that could not be generated.

    Mirrors ``IndicatorBatchItemResult``'s failure shape
    (``app/schemas/indicators.py``) deliberately: the dataset builder's
    partial-success behaviour (see ``dataset.py``) is the same pattern the
    indicator batch endpoint already established, so the failure record
    looks the same wherever a researcher encounters it.
    """

    feature: str
    params: dict[str, Any]
    error_code: str
    error_detail: str


@dataclass(frozen=True, slots=True)
class DatasetQualityReport:
    """How trustworthy a built dataset is, and what was done about it.

    Every count here is about the *build*, not about the generic candle
    store — ``total_rows``/``duplicate_timestamps``/``missing_candles``
    describe exactly the candle range this dataset was built from, not the
    market's whole history.
    """

    #: Candles loaded before warmup trimming (== `FeatureDataset.candles_analyzed`).
    total_rows: int
    #: Rows in the finished dataset, after warmup trimming and any `limit` cap.
    rows_returned: int
    #: Rows removed because at least one requested feature was still undefined.
    rows_removed: int
    #: Null count per column, counted *before* warmup trimming — after
    #: trimming there are none, by construction, so this is what explains
    #: why rows were removed rather than merely restating that they were.
    null_counts: dict[str, int] = field(default_factory=dict)
    #: Candle timestamps appearing more than once in the loaded range.
    #: Expected to always be zero (the storage layer enforces uniqueness on
    #: `(market_id, timeframe, open_time)`) — reported as a defensive
    #: signal that the data this dataset was built from is what it claims
    #: to be, the same posture `candle_validation.py` takes toward its own
    #: exact-duplicate check.
    duplicate_timestamps: int = 0
    #: Gaps in the loaded candle range at this timeframe's cadence.
    missing_candles: int = 0
    #: Requested features that failed to generate; the dataset still
    #: builds from whichever features succeeded (see `dataset.py`).
    feature_failures: list[FeatureFailure] = field(default_factory=list)
    #: Wall-clock time spent running every requested generator.
    generation_time_ms: float = 0.0


def count_duplicate_timestamps(timestamps: Sequence[datetime]) -> int:
    """Count timestamps occurring more than once, by extra occurrence.

    Three of the same timestamp counts as two duplicates, matching how a
    researcher would describe it ("two rows I didn't ask for"), not one.
    """
    seen: set[datetime] = set()
    duplicates = 0
    for timestamp in timestamps:
        if timestamp in seen:
            duplicates += 1
        else:
            seen.add(timestamp)
    return duplicates


def count_missing_candles(timestamps: Sequence[datetime], timeframe: str) -> int:
    """Count gaps in ``timestamps`` at the cadence implied by ``timeframe``.

    Compares only the *span already loaded* (oldest to newest timestamp),
    never a wider "expected since the beginning of history" range — this
    report is about the candles this dataset actually used, not the whole
    market's completeness (that remains `candle_validation.py`'s job).
    """
    if len(timestamps) < 2:
        return 0
    ordered = sorted(timestamps)
    step = resolution_duration(timeframe)
    span = ordered[-1] - ordered[0]
    expected = int(span / step) + 1
    return max(0, expected - len(set(ordered)))
