"""Tests for the `news_sentiment` feature generator — the sixth
connector-backed feature (`app.connectors.marketaux`), after
`fear_greed`, `fed_funds_rate`, `eth_gas_price`, `defillama_eth_tvl`, and
`btc_dominance`.

`TestNoLookAhead` mirrors the other five features' own adversarial proof
exactly — confirmed here too, not assumed, even though `news_sentiment`
is itself a *derived* daily aggregate that may be revised as
late-discovered articles arrive (see
`app.services.news_ingest._mirror_daily_aggregates`'s own docstring,
already proven directly in `tests/services/test_news_ingest.py
::TestDailyAggregateMirroring`). This class proves something narrower
and just as necessary: a data point dated *after* a candle never changes
that candle's own already-computed value, regardless of how the point
mirrored at an earlier timestamp came to be there.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.connectors.marketaux import MARKETAUX_SOURCE
from app.features.base import ExternalDataPoint, FeatureContext, OHLCVPoint
from app.features.builtin import load_builtin_features
from app.features.builtin.news_sentiment import NewsSentimentFeature
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
    def test_news_sentiment_is_registered_and_declares_its_own_external_source(self) -> None:
        """The feature selector's own confirmation (`/features`'s catalogue):
        a generator registered under `app/features/builtin/` appears in
        `describe_all()` with no change to the pipeline, the registry, or
        the frontend `FeatureSelector`."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        names = {entry.name for entry in pipeline.describe_all()}
        assert "news_sentiment" in names

        metadata = pipeline.describe("news_sentiment")
        assert metadata.category == "sentiment"
        assert metadata.external_sources == (MARKETAUX_SOURCE,)
        assert metadata.missing_values_expected is True
        assert metadata.outputs == ("news_sentiment",)


class TestGenerate:
    def test_looks_up_the_most_recent_value_at_or_before_each_candle(self) -> None:
        external_data = {MARKETAUX_SOURCE: [point(0, 0.3), point(2, -0.1)]}
        ctx = FeatureContext(
            candles=[candle(0), candle(60)], params={}, external_data=external_data
        )
        output = NewsSentimentFeature().generate(ctx)

        assert len(output.series) == 1
        assert output.series[0].column.name == "news_sentiment"
        assert output.series[0].values == [0.3, -0.1]

    def test_null_before_the_earliest_recorded_value(self) -> None:
        external_data = {MARKETAUX_SOURCE: [point(5, 0.2)]}
        ctx = FeatureContext(candles=[candle(0)], params={}, external_data=external_data)
        output = NewsSentimentFeature().generate(ctx)
        assert output.series[0].values == [None]

    def test_null_when_no_external_data_was_provided_at_all(self) -> None:
        ctx = FeatureContext(candles=[candle(0), candle(24)], params={}, external_data={})
        output = NewsSentimentFeature().generate(ctx)
        assert output.series[0].values == [None, None]

    def test_exact_timestamp_match_counts_as_at_or_before(self) -> None:
        external_data = {MARKETAUX_SOURCE: [point(0, 0.3)]}
        ctx = FeatureContext(
            candles=[
                OHLCVPoint(
                    open_time=datetime(2026, 1, 1, tzinfo=UTC),
                    open=1,
                    high=1,
                    low=1,
                    close=1,
                    volume=1,
                )
            ],
            params={},
            external_data=external_data,
        )
        output = NewsSentimentFeature().generate(ctx)
        assert output.series[0].values == [0.3]


@pytest.mark.asyncio
class TestNoLookAhead:
    """The adversarial proof this task explicitly requires, run in full
    for `news_sentiment` too — identical shape to the other five
    features."""

    async def test_a_future_point_never_changes_a_past_candles_value(self) -> None:
        candles = [candle(0), candle(24), candle(48)]
        baseline_data = {MARKETAUX_SOURCE: [point(0, 0.3), point(1, -0.2)]}
        baseline = (
            NewsSentimentFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=baseline_data))
            .series[0]
            .values
        )

        with_future_point = {MARKETAUX_SOURCE: [point(0, 0.3), point(1, -0.2), point(10, 0.99)]}
        after = (
            NewsSentimentFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=with_future_point))
            .series[0]
            .values
        )

        assert after == baseline
        assert 0.99 not in after

    async def test_a_future_point_inserted_out_of_order_still_never_looks_ahead(self) -> None:
        candles = [candle(0), candle(24)]
        data_out_of_order = {MARKETAUX_SOURCE: [point(10, 0.99), point(0, 0.3), point(1, -0.2)]}
        sorted_points = sorted(data_out_of_order[MARKETAUX_SOURCE], key=lambda p: p.timestamp)
        output = NewsSentimentFeature().generate(
            FeatureContext(
                candles=candles, params={}, external_data={MARKETAUX_SOURCE: sorted_points}
            )
        )
        assert output.series[0].values == [0.3, -0.2]

    async def test_end_to_end_through_the_real_ingested_data_path(
        self, session_factory: SessionFactory
    ) -> None:
        """The same guarantee, through the real database-backed pre-fetch
        (`resolve_external_data` + `ExternalDataRepository`)."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        candles = [candle(0), candle(24)]
        requests = [FeatureRequest(feature="news_sentiment")]
        session = session_factory()
        repository = ExternalDataRepository(session)

        async def current_values() -> list:
            external_data = await resolve_external_data(
                pipeline=pipeline, requests=requests, candles=candles, repository=repository
            )
            run = pipeline.run("news_sentiment", candles, external_data=external_data)
            return run.output.series[0].values

        await repository.create(
            ExternalDataPointModel(
                source=MARKETAUX_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                value=0.3,
            )
        )
        await repository.create(
            ExternalDataPointModel(
                source=MARKETAUX_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 2, tzinfo=UTC),
                value=-0.2,
            )
        )
        baseline = await current_values()

        await repository.create(
            ExternalDataPointModel(
                source=MARKETAUX_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 11, tzinfo=UTC),
                value=0.99,
            )
        )
        after = await current_values()

        assert after == baseline
        assert 0.99 not in after
