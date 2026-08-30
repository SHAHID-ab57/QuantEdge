"""AI extension-point tests.

Most of `ai_extensions.py` is not wired into the engine — these tests exist
to pin the *shape* of each remaining contract (importable, constructible, a
real class can implement the Protocols) so a future implementer's first PR
extends a verified interface rather than discovering a typo in an unused
module. Two symbols this file used to test — `LabelSpec`/`LabelGenerator`
and `TrainValidationTestSplitter` — have been removed from `ai_extensions.py`
itself (superseded by `app.ml_datasets`'s real `TargetGenerator`/
`TargetPipeline` and `ChronologicalSplitter` respectively; see that
module's own docstring) rather than kept here as tests of dead code —
their real tests live at `tests/ml_datasets/test_targets.py`,
`tests/ml_datasets/test_pipeline.py`, and `tests/ml_datasets/test_split.py`.
`FeatureNormalizer` is the one Protocol that has since gained a real
implementer (`app.training.normalization.ColumnNormalizer`) while *staying*
here — see `tests/training/test_normalization.py` for that implementer's
own tests; this file keeps pinning the Protocol's shape itself.
"""

from app.features.ai_extensions import (
    CategoricalEncoder,
    FeatureNormalizer,
    NormalizationStats,
    SequenceWindower,
    SplitRatios,
    WindowSpec,
)
from app.features.dataset import FeatureDataset


class TestWindowSpec:
    def test_defaults_to_maximum_overlap(self) -> None:
        assert WindowSpec(window_size=30).stride == 1

    def test_accepts_a_wider_stride(self) -> None:
        assert WindowSpec(window_size=30, stride=5).stride == 5


class TestNormalizationStats:
    def test_carries_per_column_statistics(self) -> None:
        stats = NormalizationStats(column="close", mean=100.0, std=5.0, minimum=90.0, maximum=110.0)
        assert stats.column == "close"
        assert stats.mean == 100.0

    def test_statistics_are_optional_for_a_column_needing_no_scaling(self) -> None:
        # e.g. a "ratio" column already in [0, 1] (see `candle_shape` with
        # `normalize=true`) — the whole point of publishing `unit`/
        # `value_type` on `FeatureMetadata` is to let a normalizer decide
        # this per column rather than guessing.
        stats = NormalizationStats(column="candle_body")
        assert stats.mean is None


class TestSplitRatios:
    def test_defaults_sum_to_one(self) -> None:
        ratios = SplitRatios()
        assert round(ratios.train + ratios.validation + ratios.test, 6) == 1.0

    def test_accepts_custom_ratios(self) -> None:
        ratios = SplitRatios(train=0.8, validation=0.1, test=0.1)
        assert ratios.train == 0.8


class TestProtocolsAreImplementable:
    """A concrete class can satisfy each Protocol — the contract is real, not aspirational."""

    def test_sequence_windower_protocol(self) -> None:
        class _Windower:
            def window(self, dataset: FeatureDataset, spec: WindowSpec) -> list:
                return []

        windower: SequenceWindower = _Windower()
        assert windower.window(None, WindowSpec(window_size=10)) == []  # type: ignore[arg-type]

    def test_feature_normalizer_protocol(self) -> None:
        class _Normalizer:
            def fit(self, dataset: FeatureDataset, columns: object) -> list:
                return []

            def transform(self, dataset: FeatureDataset, stats: object) -> FeatureDataset:
                return dataset

        normalizer: FeatureNormalizer = _Normalizer()
        assert normalizer.fit(None, []) == []  # type: ignore[arg-type]

    def test_categorical_encoder_protocol(self) -> None:
        class _Encoder:
            def encode(self, dataset: FeatureDataset, strategy: str) -> FeatureDataset:
                return dataset

        encoder: CategoricalEncoder = _Encoder()
        assert encoder.encode(None, "one_hot") is None  # type: ignore[arg-type]
