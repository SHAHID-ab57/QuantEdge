"""Tests for the `reddit_volume`/`reddit_sentiment` feature generators
(REDDIT-SENTIMENT-CONNECTOR) — the seventh and eighth connector-backed
features, structurally identical to `news_sentiment.py`'s own shape (see
that feature's own test file, mirrored here for both).

`TestNoLookAhead` mirrors every other connector-backed feature's own
adversarial proof exactly, run for both features — each is itself a
*derived* daily aggregate that may be revised as later comments for an
already-mirrored day arrive (already proven directly in
`tests/services/test_reddit_ingest.py::TestDailyAggregateMirroring`).
This class proves something narrower and just as necessary: a data point
dated *after* a candle never changes that candle's own already-computed
value.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.connectors.reddit import REDDIT_SENTIMENT_SOURCE, REDDIT_VOLUME_SOURCE
from app.features.base import ExternalDataPoint, FeatureContext, OHLCVPoint
from app.features.builtin import load_builtin_features
from app.features.builtin.reddit_sentiment import RedditSentimentFeature
from app.features.builtin.reddit_volume import RedditVolumeFeature
from app.features.dataset import FeatureRequest
from app.features.pipeline import FeaturePipeline
from app.features.registry import default_registry
from app.models.external_data import ExternalDataPoint as ExternalDataPointModel
from app.repositories.external_data import ExternalDataRepository
from app.services.external_data_context import resolve_external_data
from tests.conftest import SessionFactory


def candle(hour: int) -> OHLCVPoint:
    return OHLCVPoint(
        open_time=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=hour),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=10.0,
    )


def point(day: int, value: float) -> ExternalDataPoint:
    return ExternalDataPoint(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=day), value=value
    )


class TestDiscovery:
    def test_reddit_volume_is_registered_and_declares_its_own_external_source(self) -> None:
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        names = {entry.name for entry in pipeline.describe_all()}
        assert "reddit_volume" in names

        metadata = pipeline.describe("reddit_volume")
        assert metadata.category == "sentiment"
        assert metadata.external_sources == (REDDIT_VOLUME_SOURCE,)
        assert metadata.missing_values_expected is True
        assert metadata.outputs == ("reddit_volume",)

    def test_reddit_sentiment_is_registered_and_declares_its_own_external_source(self) -> None:
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        names = {entry.name for entry in pipeline.describe_all()}
        assert "reddit_sentiment" in names

        metadata = pipeline.describe("reddit_sentiment")
        assert metadata.category == "sentiment"
        assert metadata.external_sources == (REDDIT_SENTIMENT_SOURCE,)
        assert metadata.missing_values_expected is True
        assert metadata.outputs == ("reddit_sentiment",)


class TestGenerateVolume:
    def test_looks_up_the_most_recent_value_at_or_before_each_candle(self) -> None:
        external_data = {REDDIT_VOLUME_SOURCE: [point(0, 12.0), point(2, 47.0)]}
        ctx = FeatureContext(
            candles=[candle(0), candle(60)], params={}, external_data=external_data
        )
        output = RedditVolumeFeature().generate(ctx)

        assert len(output.series) == 1
        assert output.series[0].column.name == "reddit_volume"
        assert output.series[0].values == [12.0, 47.0]

    def test_null_before_the_earliest_recorded_value(self) -> None:
        external_data = {REDDIT_VOLUME_SOURCE: [point(5, 30.0)]}
        ctx = FeatureContext(candles=[candle(0)], params={}, external_data=external_data)
        output = RedditVolumeFeature().generate(ctx)
        assert output.series[0].values == [None]

    def test_null_when_no_external_data_was_provided_at_all(self) -> None:
        ctx = FeatureContext(candles=[candle(0), candle(24)], params={}, external_data={})
        output = RedditVolumeFeature().generate(ctx)
        assert output.series[0].values == [None, None]

    def test_a_real_zero_comment_day_is_distinct_from_missing(self) -> None:
        """A real, recorded zero (a genuinely quiet day) must never look
        the same as "not tracked yet" — both are technically falsy but
        only one is `None`."""
        external_data = {REDDIT_VOLUME_SOURCE: [point(0, 0.0)]}
        ctx = FeatureContext(candles=[candle(0)], params={}, external_data=external_data)
        output = RedditVolumeFeature().generate(ctx)
        assert output.series[0].values == [0.0]
        assert output.series[0].values[0] is not None


class TestGenerateSentiment:
    def test_looks_up_the_most_recent_value_at_or_before_each_candle(self) -> None:
        external_data = {REDDIT_SENTIMENT_SOURCE: [point(0, 0.4), point(2, -0.15)]}
        ctx = FeatureContext(
            candles=[candle(0), candle(60)], params={}, external_data=external_data
        )
        output = RedditSentimentFeature().generate(ctx)

        assert len(output.series) == 1
        assert output.series[0].column.name == "reddit_sentiment"
        assert output.series[0].values == [0.4, -0.15]

    def test_null_before_the_earliest_recorded_value(self) -> None:
        external_data = {REDDIT_SENTIMENT_SOURCE: [point(5, 0.2)]}
        ctx = FeatureContext(candles=[candle(0)], params={}, external_data=external_data)
        output = RedditSentimentFeature().generate(ctx)
        assert output.series[0].values == [None]

    def test_null_when_no_external_data_was_provided_at_all(self) -> None:
        ctx = FeatureContext(candles=[candle(0), candle(24)], params={}, external_data={})
        output = RedditSentimentFeature().generate(ctx)
        assert output.series[0].values == [None, None]


@pytest.mark.asyncio
class TestNoLookAhead:
    """The adversarial proof this platform requires of every
    connector-backed feature, run in full for both `reddit_volume` and
    `reddit_sentiment`."""

    async def test_a_future_point_never_changes_a_past_candles_value_volume(self) -> None:
        candles = [candle(0), candle(24), candle(48)]
        baseline_data = {REDDIT_VOLUME_SOURCE: [point(0, 12.0), point(1, 30.0)]}
        baseline = (
            RedditVolumeFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=baseline_data))
            .series[0]
            .values
        )

        with_future_point = {
            REDDIT_VOLUME_SOURCE: [point(0, 12.0), point(1, 30.0), point(10, 999.0)]
        }
        after = (
            RedditVolumeFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=with_future_point))
            .series[0]
            .values
        )

        assert after == baseline
        assert 999.0 not in after

    async def test_a_future_point_never_changes_a_past_candles_value_sentiment(self) -> None:
        candles = [candle(0), candle(24), candle(48)]
        baseline_data = {REDDIT_SENTIMENT_SOURCE: [point(0, 0.3), point(1, -0.2)]}
        baseline = (
            RedditSentimentFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=baseline_data))
            .series[0]
            .values
        )

        with_future_point = {
            REDDIT_SENTIMENT_SOURCE: [point(0, 0.3), point(1, -0.2), point(10, 0.99)]
        }
        after = (
            RedditSentimentFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=with_future_point))
            .series[0]
            .values
        )

        assert after == baseline
        assert 0.99 not in after

    async def test_a_future_point_inserted_out_of_order_still_never_looks_ahead(self) -> None:
        candles = [candle(0), candle(24)]
        data_out_of_order = {
            REDDIT_VOLUME_SOURCE: [point(10, 999.0), point(0, 12.0), point(1, 30.0)]
        }
        sorted_points = sorted(data_out_of_order[REDDIT_VOLUME_SOURCE], key=lambda p: p.timestamp)
        output = RedditVolumeFeature().generate(
            FeatureContext(
                candles=candles, params={}, external_data={REDDIT_VOLUME_SOURCE: sorted_points}
            )
        )
        assert output.series[0].values == [12.0, 30.0]

    async def test_end_to_end_through_the_real_ingested_data_path(
        self, session_factory: SessionFactory
    ) -> None:
        """The same guarantee, through the real database-backed pre-fetch
        (`resolve_external_data` + `ExternalDataRepository`), for both
        features at once."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        candles = [candle(0), candle(24)]
        requests = [
            FeatureRequest(feature="reddit_volume"),
            FeatureRequest(feature="reddit_sentiment"),
        ]
        session = session_factory()
        repository = ExternalDataRepository(session)

        async def current_values() -> tuple[list, list]:
            external_data = await resolve_external_data(
                pipeline=pipeline, requests=requests, candles=candles, repository=repository
            )
            volume_run = pipeline.run("reddit_volume", candles, external_data=external_data)
            sentiment_run = pipeline.run("reddit_sentiment", candles, external_data=external_data)
            return volume_run.output.series[0].values, sentiment_run.output.series[0].values

        await repository.create(
            ExternalDataPointModel(
                source=REDDIT_VOLUME_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                value=12.0,
            )
        )
        await repository.create(
            ExternalDataPointModel(
                source=REDDIT_SENTIMENT_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                value=0.3,
            )
        )
        baseline_volume, baseline_sentiment = await current_values()

        await repository.create(
            ExternalDataPointModel(
                source=REDDIT_VOLUME_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 11, tzinfo=UTC),
                value=999.0,
            )
        )
        await repository.create(
            ExternalDataPointModel(
                source=REDDIT_SENTIMENT_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 11, tzinfo=UTC),
                value=0.99,
            )
        )
        after_volume, after_sentiment = await current_values()

        assert after_volume == baseline_volume
        assert 999.0 not in after_volume
        assert after_sentiment == baseline_sentiment
        assert 0.99 not in after_sentiment
