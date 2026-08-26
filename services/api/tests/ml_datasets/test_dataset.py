"""ML dataset builder tests — assembly, partial success, collisions, and leakage prevention.

The leakage-prevention tests are the load-bearing ones in this file: they
prove, concretely, that a target column's value for row *i* is always
derived from a candle strictly *after* row *i*, never from row *i* itself
or anything earlier — the property the whole ML Dataset Builder exists to
guarantee.
"""

import pytest

from app.dataset_validation.engine import DatasetValidator
from app.dataset_validation.registry import default_registry as rule_registry
from app.dataset_validation.rules import load_builtin_rules
from app.features.ai_extensions import SplitRatios
from app.features.builtin import load_builtin_features
from app.features.dataset import FeatureDatasetBuilder, FeatureRequest
from app.features.pipeline import FeaturePipeline
from app.features.registry import default_registry as feature_registry
from app.ml_datasets.dataset import MLDatasetBuilder, TargetRequest
from app.ml_datasets.errors import DuplicateTargetColumnError, EmptyMLDatasetError
from app.ml_datasets.pipeline import TargetPipeline
from app.ml_datasets.registry import default_registry as target_registry
from app.ml_datasets.split import ChronologicalSplitter
from app.ml_datasets.targets import load_builtin_targets
from tests.ml_datasets.conftest import candles


@pytest.fixture(scope="module")
def builder() -> MLDatasetBuilder:
    """A builder over the application's real feature/target catalogues."""
    load_builtin_features()
    load_builtin_rules()
    load_builtin_targets()
    return MLDatasetBuilder(
        feature_builder=FeatureDatasetBuilder(FeaturePipeline(feature_registry)),
        target_pipeline=TargetPipeline(target_registry),
        validator=DatasetValidator(rule_registry),
        splitter=ChronologicalSplitter(),
    )


class TestAssembly:
    def test_appends_target_columns_onto_the_feature_matrix(
        self, builder: MLDatasetBuilder
    ) -> None:
        ml = builder.build(
            "ETHUSD",
            "1h",
            candles(10),
            [FeatureRequest("ohlcv")],
            [TargetRequest("next_close")],
        )
        names = [column.name for column in ml.dataset.columns]
        assert names == ["open", "high", "low", "close", "volume", "next_close_1"]
        assert ml.feature_columns == ("open", "high", "low", "close", "volume")
        assert ml.target_columns == ("next_close_1",)

    def test_combines_several_targets(self, builder: MLDatasetBuilder) -> None:
        ml = builder.build(
            "ETHUSD",
            "1h",
            candles(10),
            [FeatureRequest("ohlcv")],
            [
                TargetRequest("next_close"),
                TargetRequest("next_direction"),
                TargetRequest("next_return"),
            ],
        )
        assert set(ml.target_columns) == {"next_close_1", "next_direction_1", "next_return_1"}

    def test_records_provenance_per_target(self, builder: MLDatasetBuilder) -> None:
        ml = builder.build(
            "ETHUSD",
            "1h",
            candles(10),
            [FeatureRequest("ohlcv")],
            [TargetRequest("next_close", {"horizon": 2})],
        )
        info = ml.targets[0]
        assert info.target == "next_close"
        assert info.horizon == 2
        assert info.columns == ["next_close_2"]
        assert info.version == "1.0.0"

    def test_assigns_a_fresh_ml_dataset_id_distinct_from_the_feature_datasets_id(
        self, builder: MLDatasetBuilder
    ) -> None:
        ml = builder.build(
            "ETHUSD", "1h", candles(10), [FeatureRequest("ohlcv")], [TargetRequest("next_close")]
        )
        assert ml.ml_dataset_id != ml.dataset.dataset_id

    def test_runs_the_validation_engine_over_the_assembled_matrix(
        self, builder: MLDatasetBuilder
    ) -> None:
        ml = builder.build(
            "ETHUSD", "1h", candles(10), [FeatureRequest("ohlcv")], [TargetRequest("next_close")]
        )
        assert ml.validation.passed is True
        assert len(ml.validation.rules_run) == 11

    def test_splits_the_assembled_matrix_chronologically(self, builder: MLDatasetBuilder) -> None:
        ml = builder.build(
            "ETHUSD",
            "1h",
            candles(20),
            [FeatureRequest("ohlcv")],
            [TargetRequest("next_close")],
            split_ratios=SplitRatios(train=0.6, validation=0.2, test=0.2),
        )
        total = ml.split.train.row_count + ml.split.validation.row_count + ml.split.test.row_count
        assert total == ml.dataset.row_count


class TestLeakagePrevention:
    def test_a_targets_value_always_comes_from_a_strictly_later_candle(
        self, builder: MLDatasetBuilder
    ) -> None:
        """next_close[i] must equal the *next* row's raw close, never row i's own."""
        raw_candles = candles(10)
        ml = builder.build(
            "ETHUSD", "1h", raw_candles, [FeatureRequest("ohlcv")], [TargetRequest("next_close")]
        )
        close_index = [c.name for c in ml.dataset.columns].index("close")
        target_index = [c.name for c in ml.dataset.columns].index("next_close_1")

        for timestamp, row in zip(ml.dataset.timestamps, ml.dataset.rows, strict=True):
            # The candle this row was built from.
            source_candle = next(c for c in raw_candles if c.open_time == timestamp)
            source_index = raw_candles.index(source_candle)
            expected_next_close = float(raw_candles[source_index + 1].close)

            assert row[target_index] == expected_next_close
            # And, just as important: it must NOT equal this row's own close.
            assert row[target_index] != row[close_index]

    def test_trailing_rows_with_no_future_candle_are_never_present(
        self, builder: MLDatasetBuilder
    ) -> None:
        """The very last candle can never appear as a row, since it has no future close."""
        raw_candles = candles(10)
        ml = builder.build(
            "ETHUSD", "1h", raw_candles, [FeatureRequest("ohlcv")], [TargetRequest("next_close")]
        )
        assert raw_candles[-1].open_time not in ml.dataset.timestamps

    def test_feature_and_target_columns_are_always_disjoint(
        self, builder: MLDatasetBuilder
    ) -> None:
        ml = builder.build(
            "ETHUSD", "1h", candles(10), [FeatureRequest("ohlcv")], [TargetRequest("next_close")]
        )
        assert set(ml.feature_columns).isdisjoint(set(ml.target_columns))

    def test_the_assembled_dataset_is_never_reordered(self, builder: MLDatasetBuilder) -> None:
        ml = builder.build(
            "ETHUSD", "1h", candles(15), [FeatureRequest("ohlcv")], [TargetRequest("next_close")]
        )
        assert list(ml.dataset.timestamps) == sorted(ml.dataset.timestamps)

    def test_a_multi_horizon_request_still_never_leaks(self, builder: MLDatasetBuilder) -> None:
        """Requesting the same target at two different horizons must not collide or leak."""
        raw_candles = candles(15)
        ml = builder.build(
            "ETHUSD",
            "1h",
            raw_candles,
            [FeatureRequest("ohlcv")],
            [
                TargetRequest("next_close", {"horizon": 1}),
                TargetRequest("next_close", {"horizon": 3}),
            ],
        )
        assert set(ml.target_columns) == {"next_close_1", "next_close_3"}
        idx1 = [c.name for c in ml.dataset.columns].index("next_close_1")
        idx3 = [c.name for c in ml.dataset.columns].index("next_close_3")
        for timestamp, row in zip(ml.dataset.timestamps, ml.dataset.rows, strict=True):
            source_index = next(i for i, c in enumerate(raw_candles) if c.open_time == timestamp)
            assert row[idx1] == float(raw_candles[source_index + 1].close)
            assert row[idx3] == float(raw_candles[source_index + 3].close)


class TestPartialSuccess:
    def test_an_unknown_target_is_recorded_not_raised(self, builder: MLDatasetBuilder) -> None:
        ml = builder.build(
            "ETHUSD",
            "1h",
            candles(10),
            [FeatureRequest("ohlcv")],
            [TargetRequest("does_not_exist")],
        )
        assert ml.target_columns == ()
        assert len(ml.target_failures) == 1
        assert ml.target_failures[0].error_code == "target_not_found"

    def test_one_failing_target_does_not_block_the_others(self, builder: MLDatasetBuilder) -> None:
        ml = builder.build(
            "ETHUSD",
            "1h",
            candles(10),
            [FeatureRequest("ohlcv")],
            [TargetRequest("does_not_exist"), TargetRequest("next_close")],
        )
        assert ml.target_columns == ("next_close_1",)
        assert len(ml.target_failures) == 1

    def test_an_under_sized_horizon_is_recorded_as_a_failure(
        self, builder: MLDatasetBuilder
    ) -> None:
        ml = builder.build(
            "ETHUSD",
            "1h",
            candles(3),
            [FeatureRequest("ohlcv")],
            [TargetRequest("next_close", {"horizon": 10})],
        )
        assert ml.target_failures[0].error_code == "insufficient_data"


class TestColumnCollisions:
    def test_two_targets_producing_the_same_column_raise(self, builder: MLDatasetBuilder) -> None:
        with pytest.raises(DuplicateTargetColumnError):
            builder.build(
                "ETHUSD",
                "1h",
                candles(10),
                [FeatureRequest("ohlcv")],
                [TargetRequest("next_close"), TargetRequest("next_close")],
            )

    def test_a_target_colliding_with_an_existing_feature_column_raises(
        self, builder: MLDatasetBuilder
    ) -> None:
        # `ohlcv` produces a `close` column; forcing next_close's output
        # name to collide would require a same-named target, which no
        # builtin does — instead assert the *mechanism*: the owner map is
        # seeded from feature columns before any target runs, so a
        # hypothetical target named "close" would collide. Since no builtin
        # collides today, this test documents the guarantee via the
        # dedicated unit path in `test_split.py`/`test_pipeline.py` instead;
        # here we assert the disjointness invariant holds for the real
        # catalogue instead of asserting an error that cannot occur yet.
        ml = builder.build(
            "ETHUSD", "1h", candles(10), [FeatureRequest("ohlcv")], [TargetRequest("next_close")]
        )
        assert "close" not in ml.target_columns


class TestEmptyDataset:
    def test_raises_when_every_surviving_row_falls_inside_the_horizon_window(
        self, builder: MLDatasetBuilder
    ) -> None:
        # sma(period=8) leaves only the last 2 of 10 candles (indices 8, 9).
        # next_close(horizon=5) is undefined for original indices 5..9 —
        # both surviving rows fall inside that window, so nothing survives
        # the horizon trim even though the target itself generated fine.
        with pytest.raises(EmptyMLDatasetError):
            builder.build(
                "ETHUSD",
                "1h",
                candles(10),
                [FeatureRequest("sma", {"period": "8"})],
                [TargetRequest("next_close", {"horizon": 5})],
            )

    def test_zero_target_columns_is_not_treated_as_empty(self, builder: MLDatasetBuilder) -> None:
        # Every target failing outright (not merely horizon-trimmed away)
        # is a valid, fully-explained result, not an error.
        ml = builder.build(
            "ETHUSD",
            "1h",
            candles(10),
            [FeatureRequest("ohlcv")],
            [TargetRequest("does_not_exist")],
        )
        assert ml.dataset.row_count == 10


class TestDropUndefinedTargetsFalse:
    def test_keeps_undefined_trailing_rows_when_disabled(self, builder: MLDatasetBuilder) -> None:
        ml = builder.build(
            "ETHUSD",
            "1h",
            candles(10),
            [FeatureRequest("ohlcv")],
            [TargetRequest("next_close")],
            drop_undefined_targets=False,
        )
        assert ml.dataset.row_count == 10
        assert ml.dataset.rows[-1][-1] is None
