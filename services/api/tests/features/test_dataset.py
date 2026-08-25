"""Feature dataset builder tests — assembly, collisions, trimming, provenance.

The builder owns the three things only it can see, because it is the only
component handed more than one generator at a time: column collisions,
warmup trimming across features with different windows, and the
reproducibility record.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.features.base import OHLCVPoint
from app.features.builtin import load_builtin_features
from app.features.dataset import FeatureDatasetBuilder, FeatureRequest
from app.features.errors import DuplicateFeatureColumnError, EmptyDatasetError
from app.features.pipeline import PIPELINE_VERSION, FeaturePipeline
from app.features.registry import default_registry


@pytest.fixture(scope="module")
def builder() -> FeatureDatasetBuilder:
    """A builder over the application's real feature catalogue."""
    load_builtin_features()
    return FeatureDatasetBuilder(FeaturePipeline(default_registry))


def candles(count: int) -> list[OHLCVPoint]:
    """An ascending candle series with a non-zero range on every bar."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        OHLCVPoint(
            open_time=base + timedelta(hours=i),
            open=100.0 + i,
            high=105.0 + i,
            low=95.0 + i,
            close=102.0 + i,
            volume=10.0 + i,
        )
        for i in range(count)
    ]


class TestAssembly:
    def test_builds_one_column_per_feature_output(self, builder: FeatureDatasetBuilder) -> None:
        dataset = builder.build(
            "ETHUSD", "1h", candles(5), [FeatureRequest("ohlcv")], drop_warmup=False
        )
        assert [c.name for c in dataset.columns] == [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

    def test_combines_several_features_into_one_matrix(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(6),
            [
                FeatureRequest("ohlcv"),
                FeatureRequest("candle_shape"),
                FeatureRequest("sma", {"period": "3"}),
            ],
        )
        names = [c.name for c in dataset.columns]
        assert "open" in names
        assert "candle_body" in names
        assert "sma_3" in names

    def test_every_row_has_one_value_per_column(self, builder: FeatureDatasetBuilder) -> None:
        dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(6),
            [FeatureRequest("ohlcv"), FeatureRequest("sma", {"period": "2"})],
        )
        for row in dataset.rows:
            assert len(row) == len(dataset.columns)

    def test_rows_stay_aligned_with_timestamps(self, builder: FeatureDatasetBuilder) -> None:
        dataset = builder.build(
            "ETHUSD", "1h", candles(4), [FeatureRequest("ohlcv")], drop_warmup=False
        )
        assert len(dataset.timestamps) == len(dataset.rows)
        # The `open` column is the first, and candle N opens at 100 + N.
        assert [row[0] for row in dataset.rows] == [100.0, 101.0, 102.0, 103.0]

    def test_column_order_follows_request_order(self, builder: FeatureDatasetBuilder) -> None:
        dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(5),
            [FeatureRequest("sma", {"period": "2"}), FeatureRequest("ohlcv")],
        )
        assert dataset.columns[0].name == "sma_2"
        assert dataset.columns[1].name == "open"

    def test_builds_an_empty_dataset_from_no_requests(self, builder: FeatureDatasetBuilder) -> None:
        dataset = builder.build("ETHUSD", "1h", candles(3), [])
        assert dataset.columns == []
        assert dataset.row_count == 0

    def test_exposes_its_pipeline(self, builder: FeatureDatasetBuilder) -> None:
        assert builder.pipeline.registry.has("ohlcv")


class TestColumnCollisions:
    def test_rejects_two_features_producing_the_same_column(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        # A silently overwritten column is the worst possible dataset
        # defect: the model trains on data nobody intended.
        with pytest.raises(DuplicateFeatureColumnError) as exc_info:
            builder.build(
                "ETHUSD",
                "1h",
                candles(5),
                [
                    FeatureRequest("sma", {"period": "2"}),
                    FeatureRequest("sma", {"period": "2"}),
                ],
            )
        assert "sma_2" in exc_info.value.message

    def test_the_same_feature_at_different_periods_is_allowed(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(6),
            [
                FeatureRequest("sma", {"period": "2"}),
                FeatureRequest("sma", {"period": "3"}),
            ],
        )
        assert [c.name for c in dataset.columns] == ["sma_2", "sma_3"]


class TestWarmupTrimming:
    def test_drops_rows_where_any_feature_is_still_undefined(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        dataset = builder.build(
            "ETHUSD", "1h", candles(6), [FeatureRequest("sma", {"period": "3"})]
        )
        assert dataset.row_count == 4
        assert dataset.rows_dropped == 2
        assert dataset.warmup_candles == 3

    def test_trimming_is_driven_by_the_longest_warmup(self, builder: FeatureDatasetBuilder) -> None:
        # ohlcv needs 0 candles, sma(4) needs 4 — the dataset is only
        # complete once the slowest feature is.
        dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(8),
            [FeatureRequest("ohlcv"), FeatureRequest("sma", {"period": "4"})],
        )
        assert dataset.warmup_candles == 4
        assert dataset.row_count == 5

    def test_no_row_in_a_trimmed_dataset_contains_a_null(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        # The property that makes the output a *training matrix*.
        dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(8),
            [FeatureRequest("sma", {"period": "3"}), FeatureRequest("ema", {"period": "4"})],
        )
        assert dataset.rows
        for row in dataset.rows:
            assert None not in row

    def test_keeps_warmup_rows_when_trimming_is_disabled(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(6),
            [FeatureRequest("sma", {"period": "3"})],
            drop_warmup=False,
        )
        assert dataset.row_count == 6
        assert dataset.rows_dropped == 0
        assert dataset.rows[0][0] is None  # warmup preserved

    def test_drops_a_mid_series_null_not_only_leading_ones(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        # A flat candle's normalized wick fractions are undefined. That row
        # is as unusable to a model as a leading warmup row, so the rule is
        # "complete rows only" rather than "leading rows only".
        bars = candles(4)
        flat = OHLCVPoint(
            open_time=bars[2].open_time, open=50.0, high=50.0, low=50.0, close=50.0, volume=1.0
        )
        bars[2] = flat
        dataset = builder.build(
            "ETHUSD", "1h", bars, [FeatureRequest("candle_shape", {"normalize": "true"})]
        )
        assert dataset.row_count == 3
        assert dataset.rows_dropped == 1

    def test_reports_the_warmup_needed_before_loading_anything(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        # The service widens its candle window by this, so adding a
        # longer-period feature never silently shrinks a dataset.
        warmup = builder.required_warmup(
            [FeatureRequest("ohlcv"), FeatureRequest("sma", {"period": "50"})]
        )
        assert warmup == 50

    def test_required_warmup_of_no_requests_is_zero(self, builder: FeatureDatasetBuilder) -> None:
        assert builder.required_warmup([]) == 0

    def test_records_a_range_shorter_than_a_features_warmup_as_a_failure(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        # Distinct from "no candles stored": the range had data, but the
        # period was longer than the range. This is a per-feature outcome —
        # recorded in the quality report, not raised — mirroring the
        # indicator batch endpoint's partial-success contract: one
        # feature's bad range must not blank out every other one requested
        # alongside it.
        dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(3),
            [FeatureRequest("ohlcv"), FeatureRequest("sma", {"period": "10"})],
        )
        assert [c.name for c in dataset.columns] == [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
        failure = dataset.quality.feature_failures[0]
        assert failure.feature == "sma"
        assert failure.error_code == "insufficient_data"
        assert "10" in failure.error_detail
        assert "3" in failure.error_detail

    def test_raises_when_every_row_is_incomplete_despite_enough_candles(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        # The residual case warmup enforcement cannot catch: enough candles,
        # but every row still holds a null (here, every candle is flat, so
        # no normalized wick fraction is defined).
        flat = [
            OHLCVPoint(
                open_time=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=i),
                open=50.0,
                high=50.0,
                low=50.0,
                close=50.0,
                volume=1.0,
            )
            for i in range(4)
        ]
        with pytest.raises(EmptyDatasetError) as exc_info:
            builder.build(
                "ETHUSD", "1h", flat, [FeatureRequest("candle_shape", {"normalize": "true"})]
            )
        assert exc_info.value.code == "empty_dataset"
        assert "Widen the date range" in exc_info.value.message


class TestPartialSuccess:
    """One requested feature failing must not abort the others.

    Mirrors `IndicatorService.calculate_batch`'s partial-success contract
    exactly — the same reasoning applies here: a misconfigured feature is
    a fact about *that* feature, not about the dataset as a whole.
    """

    def test_an_unknown_feature_is_recorded_not_raised(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        dataset = builder.build(
            "ETHUSD", "1h", candles(5), [FeatureRequest("ohlcv"), FeatureRequest("nope")]
        )
        assert [c.name for c in dataset.columns] == [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
        failure = dataset.quality.feature_failures[0]
        assert failure.feature == "nope"
        assert failure.error_code == "feature_not_found"

    def test_an_invalid_parameter_is_recorded_not_raised(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        dataset = builder.build(
            "ETHUSD",
            "1h",
            candles(5),
            [FeatureRequest("ohlcv"), FeatureRequest("sma", {"period": "0"})],
        )
        assert dataset.columns  # ohlcv still succeeded
        failure = dataset.quality.feature_failures[0]
        assert failure.feature == "sma"
        assert failure.error_code == "invalid_feature_parameter"

    def test_every_feature_failing_yields_a_valid_empty_dataset(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        # Zero columns because everything failed is a different case from
        # "every row was warmup" — it must not raise EmptyDatasetError,
        # since the quality report already explains it fully.
        dataset = builder.build("ETHUSD", "1h", candles(5), [FeatureRequest("nope")])
        assert dataset.columns == []
        assert dataset.row_count == 0
        assert len(dataset.quality.feature_failures) == 1

    def test_a_column_collision_still_raises_rather_than_recording_a_failure(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        # Unlike a per-feature runtime failure, a column collision is a
        # request-shape problem with no partial result that would make
        # sense — it must still hard-fail the whole build.
        with pytest.raises(DuplicateFeatureColumnError):
            builder.build(
                "ETHUSD",
                "1h",
                candles(5),
                [
                    FeatureRequest("sma", {"period": "2"}),
                    FeatureRequest("sma", {"period": "2"}),
                ],
            )


class TestProvenance:
    def test_records_the_pipeline_version(self, builder: FeatureDatasetBuilder) -> None:
        dataset = builder.build("ETHUSD", "1h", candles(3), [FeatureRequest("ohlcv")])
        assert dataset.pipeline_version == PIPELINE_VERSION

    def test_records_each_features_resolved_parameters(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        # Resolved, not requested: defaults applied, so the record names the
        # values that actually ran.
        dataset = builder.build(
            "ETHUSD", "1h", candles(5), [FeatureRequest("sma", {"period": "2"})]
        )
        info = dataset.features[0]
        assert info.params == {"period": 2, "source": "close"}

    def test_records_each_features_version_and_columns(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        dataset = builder.build(
            "ETHUSD", "1h", candles(5), [FeatureRequest("sma", {"period": "2"})]
        )
        info = dataset.features[0]
        assert info.feature == "sma"
        assert info.version == "1.0.0"
        assert info.columns == ["sma_2"]
        assert info.warmup == 2
        assert info.execution_time_ms >= 0.0

    def test_records_the_market_and_timeframe(self, builder: FeatureDatasetBuilder) -> None:
        dataset = builder.build("ETHUSD", "4h", candles(3), [FeatureRequest("ohlcv")])
        assert dataset.symbol == "ETHUSD"
        assert dataset.timeframe == "4h"

    def test_records_candle_volume_before_trimming(self, builder: FeatureDatasetBuilder) -> None:
        dataset = builder.build(
            "ETHUSD", "1h", candles(6), [FeatureRequest("sma", {"period": "3"})]
        )
        assert dataset.candles_analyzed == 6
        assert dataset.row_count == 4

    def test_stamps_a_generation_time(self, builder: FeatureDatasetBuilder) -> None:
        dataset = builder.build("ETHUSD", "1h", candles(3), [FeatureRequest("ohlcv")])
        assert dataset.generated_at.tzinfo is not None
