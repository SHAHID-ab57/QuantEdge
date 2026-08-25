"""Where future ML capabilities plug into the Feature Engineering Engine.

Documents the seams a training/inference pipeline would need, without
speculatively implementing any of them — the same discipline
`apps/dashboard/src/features/replay/extension-points.ts` already applies to
the Replay engine's own unbuilt capabilities, and for the same reason:
nothing below is wired into `FeatureDatasetBuilder`, `FeaturePipeline`, or
any API endpoint today. It exists so a future implementer has a concrete
contract to extend rather than needing to re-architect the dataset builder
around requirements nobody has stated yet (`docs/ai/AI.md` § "Training
Pipeline"/"Inference"/"Evaluation" — all "not built").

## Why these six and not others

``PROJECT.md``'s stated ML pipeline is: engineered features → labelled,
windowed training examples → a trained model → backtested/evaluated
predictions. Everything below is a step on that path that has not been
built. Each interface is deliberately the *smallest* contract that would
let a real implementation slot in beside ``FeatureDataset`` without
changing its shape — every one of them consumes or produces a
``FeatureDataset`` (or the row/column primitives it's built from) rather
than a parallel data structure, so a future training job reuses the exact
matrix a researcher already inspected and exported, not a re-derived copy
that could silently disagree with it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from app.features.base import FeatureValue
from app.features.dataset import FeatureDataset

# --------------------------------------------------------------------------
# 1. Labels and targets
# --------------------------------------------------------------------------
#
# A `FeatureDataset` has no notion of "the thing being predicted" — every
# column is an input. A future label generator would add exactly one more
# column to the same matrix (e.g. "close price N candles ahead", "did price
# rise more than X% within N candles"), computed the same way every other
# feature is: one pass over candles, aligned index-for-index. It is
# deliberately *not* a `FeatureGenerator` today, because a label is defined
# relative to the *future* — it looks ahead of the row it is attached to,
# which none of the eight warmup-only (look-behind) generators do, and
# mixing that assumption into the existing contract without a real
# consumer to validate it against would be exactly the kind of speculative
# change this module exists to avoid making silently.


@dataclass(frozen=True, slots=True)
class LabelSpec:
    """What a future label generator would need to declare about itself.

    Deliberately parallel to `FeatureColumn`/`FeatureMetadata`: a label is
    a column like any other, plus one fact nothing else needs — how far
    into the future it looks, so a consumer knows how many trailing rows
    have no valid label yet (the mirror image of a feature's *warmup*).
    """

    name: str
    label: str
    description: str
    horizon_candles: int


class LabelGenerator(Protocol):
    """A future counterpart to `FeatureGenerator`, for target columns.

    Given the same candles a feature generator would receive, produce one
    aligned column whose trailing `horizon_candles` positions are `None`
    (the label needs candles that haven't happened yet within the loaded
    range) — the same "null marks undefined, never fabricated" contract
    `FeatureOutput` already uses, mirrored at the other end of the series.
    """

    spec: LabelSpec

    def generate_labels(
        self, candles: Sequence[object]
    ) -> list[FeatureValue]: ...  # pragma: no cover - contract only


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
    validation/test statistics into training — see `TrainValidationTestSplit`
    below, which this is meant to be used downstream of, not instead of.
    """

    def fit(
        self, dataset: FeatureDataset, columns: Sequence[str]
    ) -> list[NormalizationStats]: ...  # pragma: no cover - contract only

    def transform(
        self, dataset: FeatureDataset, stats: Sequence[NormalizationStats]
    ) -> FeatureDataset: ...  # pragma: no cover - contract only


# --------------------------------------------------------------------------
# 4. Train / validation / test splitting
# --------------------------------------------------------------------------
#
# A time-series split, not a random one: shuffling rows before splitting
# would leak future information into a "training" row sitting next to a
# "test" row from earlier in time — the same look-ahead bias
# `InsufficientFeatureDataError`'s warmup enforcement already exists to
# keep out of a single dataset, now at the split boundary instead. All
# three splits are contiguous, chronologically ordered slices of one
# dataset — train, then validation, then test — never interleaved.


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


class TrainValidationTestSplitter(Protocol):
    """Splits one dataset into three chronologically-ordered slices.

    Every output dataset keeps the *same* `dataset_id`-worthy provenance
    fields (`pipeline_version`, each feature's resolved parameters) as the
    dataset it was split from — a split is a view over one build, not three
    independent ones, so nothing about *how the data was generated*
    changes at the split boundary, only which rows are visible.
    """

    def split(
        self, dataset: FeatureDataset, ratios: SplitRatios
    ) -> DatasetSplit: ...  # pragma: no cover - contract only


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
