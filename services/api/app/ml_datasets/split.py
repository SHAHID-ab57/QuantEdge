"""Chronological train/validation/test splitting.

Implements `app.features.ai_extensions.TrainValidationTestSplitter` — the
documented-but-unwired extension point the Feature Engineering Engine's
usability review scaffolded for exactly this purpose. `SplitRatios` and
`DatasetSplit` are imported from there and used as-is, not redeclared: this
is that extension point's first real implementer, not a second, parallel
splitting mechanism.

The one rule this whole module exists to enforce: **splits are contiguous,
chronologically-ordered slices — train, then validation, then test, never
shuffled and never interleaved.** Shuffling rows before splitting would let
a "training" row sit next to, or after, a "test" row from earlier in time,
which is look-ahead bias at the split boundary — the same failure mode
warmup/horizon trimming already guards against within a single row.
"""

from dataclasses import replace

from app.features.ai_extensions import DatasetSplit, SplitRatios
from app.features.dataset import FeatureDataset
from app.ml_datasets.errors import InvalidSplitRatiosError

#: Floating-point ratios rarely sum to exactly 1.0; this is the tolerance
#: for "close enough," matching common floating-point-sum-of-fractions
#: slack (e.g. 0.7 + 0.15 + 0.15 in IEEE 754 is not bit-exact).
_RATIO_TOLERANCE = 1e-6


class ChronologicalSplitter:
    """Splits one dataset into three contiguous, time-ordered slices.

    A structural, not incidental, guarantee: rows are never reordered or
    resampled here, only sliced by contiguous index range — the dataset
    builder that produced ``dataset`` already guarantees its rows are in
    ascending candle order, and this class never does anything that could
    violate that. Every slice keeps the parent's own ``dataset_id``: a
    split is a view over one build, not three independent ones, so nothing
    about *how the data was generated* changes at the split boundary, only
    which rows are visible (see `DatasetSplit`'s own docstring).
    """

    def split(self, dataset: FeatureDataset, ratios: SplitRatios) -> DatasetSplit:
        """Slice ``dataset`` into train/validation/test, in that chronological order."""
        _validate_ratios(ratios)
        total = dataset.row_count
        train_end = int(total * ratios.train)
        validation_end = train_end + int(total * ratios.validation)
        # The test split absorbs whatever floor()-rounding left over, so
        # every row belongs to exactly one split and none are silently
        # dropped at the boundary.
        validation_end = min(validation_end, total)

        return DatasetSplit(
            train=_slice(dataset, 0, train_end),
            validation=_slice(dataset, train_end, validation_end),
            test=_slice(dataset, validation_end, total),
        )


def _validate_ratios(ratios: SplitRatios) -> None:
    """Every ratio non-negative, summing to 1.0, with a non-empty train split."""
    for name, value in (
        ("train", ratios.train),
        ("validation", ratios.validation),
        ("test", ratios.test),
    ):
        if value < 0:
            raise InvalidSplitRatiosError(f"{name} must be >= 0, got {value}")
    if ratios.train <= 0:
        raise InvalidSplitRatiosError(
            "train must be > 0 — a dataset with no training rows is useless"
        )
    total = ratios.train + ratios.validation + ratios.test
    if abs(total - 1.0) > _RATIO_TOLERANCE:
        raise InvalidSplitRatiosError(
            f"train + validation + test must sum to 1.0, got {total} "
            f"(train={ratios.train}, validation={ratios.validation}, test={ratios.test})"
        )


def _slice(dataset: FeatureDataset, start: int, end: int) -> FeatureDataset:
    """A contiguous row range of ``dataset``, keeping its own identity and provenance.

    Only ``timestamps``/``rows`` (what this slice actually contains) and
    ``quality.rows_returned`` (what this response actually hands back —
    the same field ``FeatureService._cap_rows`` already updates when
    capping for ``limit``) change. Everything else — ``dataset_id``,
    ``candles_analyzed``, ``rows_dropped``, ``quality.total_rows``,
    duplicate/missing-candle counts, feature failures — describes the
    *build*, not this view over it, and stays identical across all three
    slices: that is exactly what "a split is a view over one build, not
    three independent ones" means in practice.

    Uses `dataclasses.replace` rather than reconstructing `FeatureDataset`
    field-for-field, so a future field added to that type is automatically
    carried through a split with no change needed here.
    """
    rows = dataset.rows[start:end]
    return replace(
        dataset,
        timestamps=dataset.timestamps[start:end],
        rows=rows,
        quality=replace(dataset.quality, rows_returned=len(rows)),
    )
