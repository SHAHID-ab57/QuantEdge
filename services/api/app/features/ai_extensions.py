"""Where future ML capabilities plug into the Feature Engineering Engine.

Documents the seams a training/inference pipeline would need, without
speculatively implementing any of them — the same discipline
`apps/dashboard/src/features/replay/extension-points.ts` already applies to
the Replay engine's own unbuilt capabilities, and for the same reason.
Two of the four sections below (train/validation/test splitting, feature
normalization) have since gained real implementers elsewhere on this
platform — each says so explicitly where it is declared, rather than this
module quietly going stale. A third (labels/targets) was fully superseded
by the real `app.ml_datasets` context and has been removed outright, not
merely marked stale, so this file never implies two competing ways to do
the same thing. Only sliding-window sequencing and categorical encoding
remain genuinely unimplemented, speculative extension points today.

## Why these and not others

``PROJECT.md``'s stated ML pipeline is: engineered features → labelled,
windowed training examples → a trained model → backtested/evaluated
predictions. Each interface below is deliberately the *smallest* contract
that would let a real implementation slot in beside ``FeatureDataset``
without changing its shape — every one of them consumes or produces a
``FeatureDataset`` (or the row/column primitives it's built from) rather
than a parallel data structure, so a future consumer reuses the exact
matrix a researcher already inspected and exported, not a re-derived copy
that could silently disagree with it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from app.features.base import FeatureValue
from app.features.dataset import FeatureDataset

# --------------------------------------------------------------------------
# 1. Labels and targets — REMOVED, superseded by a real implementation
# --------------------------------------------------------------------------
#
# This section used to document a future `LabelSpec`/`LabelGenerator`
# extension point: a forward-looking column, aligned to candles, whose
# trailing `horizon_candles` positions are undefined. That is exactly what
# `app.ml_datasets.base`'s `TargetMetadata`/`TargetGenerator`/`TargetPipeline`
# already build, in their own registry, deliberately separate from the
# feature registry (see that module's own docstring for why a target lives
# apart from a feature). Keeping both a
# real implementation and an unimplemented "future" stub describing the
# same concept invited exactly the "two competing ways to do targets" this
# module's own docstring warns against, so the stub was deleted rather than
# left to drift out of sync with what actually shipped. The real tests live
# at `tests/ml_datasets/test_targets.py` and `tests/ml_datasets/test_pipeline.py`.

# --------------------------------------------------------------------------
# 2. Sliding windows and sequence generation
# --------------------------------------------------------------------------
#
# `FeatureDataset.rows` is one row per candle — the shape a classical
# (non-sequential) model wants. A sequence model (an RNN/transformer/CNN
# over time) instead wants overlapping windows of W consecutive rows each.
# That reshaping is a pure function *of* a `FeatureDataset`, not a new data
# source — it never needs a second database query or a second feature
# computation, only a different way of slicing rows that already exist.


@dataclass(frozen=True, slots=True)
class WindowSpec:
    """How to slice a dataset's rows into overlapping sequences."""

    #: Rows per window (a sequence model's input length).
    window_size: int
    #: Rows to advance between windows; `1` yields the maximum overlap
    #: (every possible window), matching how a live inference path would
    #: see one new row at a time.
    stride: int = 1


class SequenceWindower(Protocol):
    """Turns one dataset's rows into overlapping fixed-length sequences.

    Input and output both stay in terms of `FeatureDataset` primitives
    (`columns`, and windows of `rows`) rather than a framework-specific
    tensor type, so this stays framework-agnostic the same way
    `FeatureGenerator` does — a future PyTorch, TensorFlow, or plain-numpy
    consumer all windows the identical dataset the same way.
    """

    def window(
        self, dataset: FeatureDataset, spec: WindowSpec
    ) -> list[list[list[FeatureValue]]]: ...  # pragma: no cover - contract only


# --------------------------------------------------------------------------
# 3. Feature normalization
# --------------------------------------------------------------------------
#
# `app.training.normalization.ColumnNormalizer` is this Protocol's first real
# implementer — see that module's own docstring. Unlike section 4 below,
# this Protocol is kept here deliberately: it stays the one contract a
# caller programs against (`fit`/`transform`, over a whole `FeatureDataset`),
# and `ColumnNormalizer` is a training-time-only consumer of it, wired in at
# exactly one seam (`app/training/dataset_loader.py`) rather than inside any
# generator — see the paragraph below for why it is still never applied to
# `FeatureDatasetRequest`/`FeatureDatasetResponse` themselves.
#
# Deliberately *not* applied inside any generator today — `docs/api/API.md`
# states the platform's existing convention plainly: no rounding, scaling,
# or transformation is ever applied server-side to a value a researcher can
# inspect and export; display/model-input transforms are the consumer's
# concern. A model needs normalized inputs, but the *raw* dataset must
# remain the one source of truth everything else (a chart, an export, a
# second model with different normalization needs) is built from.
# `FeatureMetadata.unit`/`value_type` (see `base.py`) already carry exactly
# what a normalizer would need to decide *how* to normalize a column: a
# "ratio" column already in `[0, 1]` needs no rescaling; a "price" column's
# range depends on the asset and needs it.


@dataclass(frozen=True, slots=True)
class NormalizationStats:
    """Per-column statistics a normalizer would fit on a training split.

    Recorded, not just computed on demand: a model's inference path must
    apply the *training* split's statistics to new data, never its own —
    the training/serving consistency principle `docs/ai/AI.md` already
    applies to feature computation applies equally to normalization.
    """

    column: str
    mean: float | None = None
    std: float | None = None
    minimum: float | None = None
    maximum: float | None = None


class FeatureNormalizer(Protocol):
    """Fits normalization statistics on one dataset, applies them to another.

    Split into `fit`/`transform` (never a combined `fit_transform`)
    specifically so the extension point cannot be used in a way that leaks
    validation/test statistics into training — see § 4 below
    (`app.ml_datasets.split.ChronologicalSplitter`), which this is meant to
    be used downstream of, not instead of: split first, fit only on the
    resulting train slice, then transform every slice with those stats.
    """

    def fit(
        self, dataset: FeatureDataset, columns: Sequence[str]
    ) -> list[NormalizationStats]: ...  # pragma: no cover - contract only

    def transform(
        self, dataset: FeatureDataset, stats: Sequence[NormalizationStats]
    ) -> FeatureDataset: ...  # pragma: no cover - contract only


# --------------------------------------------------------------------------
# 4. Train / validation / test splitting — ALREADY IMPLEMENTED
# --------------------------------------------------------------------------
#
# Unlike every other section in this module, this one is no longer a future
# extension point: `app.ml_datasets.split.ChronologicalSplitter` is a real,
# shipped implementer of the `split(dataset, ratios) -> DatasetSplit`
# contract this section used to describe only as a `TrainValidationTestSplitter`
# Protocol — that Protocol class has been removed so this file doesn't imply
# two competing ways to split a dataset; `SplitRatios`/`DatasetSplit` below
# are kept exactly as they were, since `ChronologicalSplitter` and every
# consumer of it (`app.ml_datasets.dataset.MLDatasetBuilder`,
# `app.services.ml_datasets`, `app.services.training`) import and construct
# these two dataclasses directly, unchanged. See `app/ml_datasets/split.py`'s
# own module docstring for the split's full rationale (a time-series split,
# not a random one — shuffling rows before splitting would leak future
# information into a "training" row sitting next to a "test" row from
# earlier in time) and `tests/ml_datasets/test_split.py` for its tests.


@dataclass(frozen=True, slots=True)
class SplitRatios:
    """Fractions of a dataset's rows assigned to each split. Must sum to 1.0."""

    train: float = 0.7
    validation: float = 0.15
    test: float = 0.15


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    """The three contiguous, chronologically-ordered slices of one dataset."""

    train: FeatureDataset
    validation: FeatureDataset
    test: FeatureDataset


# --------------------------------------------------------------------------
# 5. Model input encoding
# --------------------------------------------------------------------------
#
# The one place `FeatureColumn.dtype` (`base.py`) is consumed by something
# other than a human reading a preview table: a `"categorical"` column
# (e.g. `candle_direction`'s `"up"`/`"down"`/`"flat"`) needs one-hot or
# ordinal encoding before a numeric model can consume it, while a
# `"float"`/`"int"`/`"bool"` column is already model-ready as-is. This
# extension point is what makes that a lookup against already-published
# metadata rather than a hardcoded per-column special case a future
# training job would have to maintain by hand.

CategoricalEncoding = Literal["one_hot", "ordinal"]


class CategoricalEncoder(Protocol):
    """Encodes every `"categorical"` column in a dataset for a numeric model.

    Reads `FeatureColumn.dtype` to decide *which* columns need encoding —
    never a hardcoded column-name list — so a future categorical feature
    (this platform's ninth, tenth, ...) is picked up with no change here,
    the same "add a feature, not a special case" guarantee the rest of this
    context already provides.
    """

    def encode(
        self, dataset: FeatureDataset, strategy: CategoricalEncoding
    ) -> FeatureDataset: ...  # pragma: no cover - contract only
