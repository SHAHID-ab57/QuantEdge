"""AI extension-point tests.

Nothing in `ai_extensions.py` is wired into the engine — these tests exist
to pin the *shape* of the contract (importable, constructible, a real class
can implement the Protocols) so a future implementer's first PR extends a
verified interface rather than discovering a typo in an unused module.
"""

from app.features.ai_extensions import (
    CategoricalEncoder,
    DatasetSplit,
    FeatureNormalizer,
    LabelGenerator,
    LabelSpec,
    NormalizationStats,
    SequenceWindower,
    SplitRatios,
    TrainValidationTestSplitter,
    WindowSpec,
)
from app.features.dataset import FeatureDataset


class TestLabelSpec:
    def test_declares_a_forward_looking_horizon(self) -> None:
        spec = LabelSpec(
            name="future_return_5",
            label="5-Candle Forward Return",
            description="Percent change from this candle's close to 5 candles ahead.",
            horizon_candles=5,
        )
        assert spec.horizon_candles == 5


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

    def test_label_generator_protocol(self) -> None:
        class _Labeler:
            spec = LabelSpec(name="x", label="X", description="", horizon_candles=1)

            def generate_labels(self, candles: object) -> list:
                return [None]

        labeler: LabelGenerator = _Labeler()
        assert labeler.generate_labels([]) == [None]

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

    def test_train_validation_test_splitter_protocol(self) -> None:
        class _Splitter:
            def split(self, dataset: FeatureDataset, ratios: SplitRatios) -> DatasetSplit:
                return DatasetSplit(train=dataset, validation=dataset, test=dataset)

        splitter: TrainValidationTestSplitter = _Splitter()
        result = splitter.split(None, SplitRatios())  # type: ignore[arg-type]
        assert result.train is None

    def test_categorical_encoder_protocol(self) -> None:
        class _Encoder:
            def encode(self, dataset: FeatureDataset, strategy: str) -> FeatureDataset:
                return dataset

        encoder: CategoricalEncoder = _Encoder()
        assert encoder.encode(None, "one_hot") is None  # type: ignore[arg-type]
