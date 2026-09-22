"""Tests for the `funding_rate` and `open_interest` feature generators (M4-E3-T3).

Same adversarial no-look-ahead proof every connector-backed feature carries,
plus what is specific to these two sources: funding is a *step function*
stored only at changes/funding times, so a candle between two stored points
must carry the earlier value forward, and the value stamped exactly at a
candle's own `open_time` is visible to that candle but nothing later is.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.connectors.delta_market_data import FUNDING_SOURCE, OPEN_INTEREST_SOURCE
from app.features.base import ExternalDataPoint, FeatureContext, OHLCVPoint
from app.features.builtin import load_builtin_features
from app.features.builtin.funding_rate import FundingRateFeature
from app.features.builtin.open_interest import OpenInterestFeature
from app.features.dataset import FeatureRequest
from app.features.pipeline import FeaturePipeline
from app.features.registry import default_registry
from app.models.external_data import ExternalDataPoint as ExternalDataPointModel
from app.repositories.external_data import ExternalDataRepository
from app.services.external_data_context import resolve_external_data
from tests.conftest import SessionFactory

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def candle(hour: int) -> OHLCVPoint:
    return OHLCVPoint(
        open_time=T0 + timedelta(hours=hour), open=100.0, high=101.0, low=99.0, close=100.0,
        volume=10.0,
    )  # fmt: skip


def point(hour: float, value: float) -> ExternalDataPoint:
    return ExternalDataPoint(timestamp=T0 + timedelta(hours=hour), value=value)


CASES = [
    pytest.param(FundingRateFeature, FUNDING_SOURCE, "funding_rate", id="funding_rate"),
    pytest.param(OpenInterestFeature, OPEN_INTEREST_SOURCE, "open_interest", id="open_interest"),
]


def run(feature_cls, source, candles, points) -> list:
    ctx = FeatureContext(candles=candles, params={}, external_data={source: points})
    return feature_cls().generate(ctx).series[0].values


@pytest.mark.parametrize(("feature_cls", "source", "name"), CASES)
class TestDiscoveryAndLookup:
    def test_registered_with_its_own_external_source(self, feature_cls, source, name) -> None:
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        assert name in {entry.name for entry in pipeline.describe_all()}
        metadata = pipeline.describe(name)
        assert metadata.external_sources == (source,)
        assert metadata.outputs == (name,)
        assert metadata.missing_values_expected is True
        assert metadata.category == "derivatives"

    def test_carries_the_last_value_forward_between_points(self, feature_cls, source, name) -> None:
        """A step series stored only at changes: hours 1..7 see the hour-0 value."""
        points = [point(0, 1.0), point(8, 2.0)]
        candles = [candle(h) for h in (0, 1, 7, 8, 9)]
        assert run(feature_cls, source, candles, points) == [1.0, 1.0, 1.0, 2.0, 2.0]

    def test_a_point_stamped_exactly_at_the_candle_is_visible(
        self, feature_cls, source, name
    ) -> None:
        assert run(feature_cls, source, [candle(8)], [point(8, 5.0)]) == [5.0]

    def test_a_point_one_second_after_the_candle_is_not(self, feature_cls, source, name) -> None:
        assert run(feature_cls, source, [candle(8)], [point(8 + 1 / 3600, 5.0)]) == [None]

    def test_null_before_the_first_recorded_value_and_with_no_data(
        self, feature_cls, source, name
    ) -> None:
        assert run(feature_cls, source, [candle(0)], [point(5, 1.0)]) == [None]
        ctx = FeatureContext(candles=[candle(0), candle(1)], params={}, external_data={})
        assert feature_cls().generate(ctx).series[0].values == [None, None]


@pytest.mark.asyncio
@pytest.mark.parametrize(("feature_cls", "source", "name"), CASES)
class TestNoLookAhead:
    async def test_a_future_point_never_changes_a_past_candles_value(
        self, feature_cls, source, name
    ) -> None:
        candles = [candle(0), candle(8), candle(16)]
        baseline_points = [point(0, 1.0), point(8, 2.0)]
        baseline = run(feature_cls, source, candles, baseline_points)

        poisoned = [*baseline_points, point(17, 999_999.0), point(24, 888_888.0)]
        after = run(feature_cls, source, candles, poisoned)

        assert after == baseline
        assert 999_999.0 not in after and 888_888.0 not in after

    async def test_every_value_used_was_stamped_at_or_before_its_candle(
        self, feature_cls, source, name
    ) -> None:
        """Encode each point's own timestamp (in hours) as its value, so the output
        of every candle proves which point it read: it must never exceed the candle."""
        points = [point(h, float(h)) for h in range(0, 200, 8)]
        candles = [candle(h) for h in range(0, 200)]
        values = run(feature_cls, source, candles, points)
        for c, v in zip(candles, values, strict=True):
            hour = (c.open_time - T0) / timedelta(hours=1)
            assert v is not None
            assert v <= hour

    async def test_end_to_end_through_the_real_ingested_data_path(
        self, session_factory: SessionFactory, feature_cls, source, name
    ) -> None:
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        candles = [candle(0), candle(9)]
        requests = [FeatureRequest(feature=name)]
        repository = ExternalDataRepository(session_factory())

        async def current() -> list:
            external = await resolve_external_data(
                pipeline=pipeline, requests=requests, candles=candles, repository=repository
            )
            return pipeline.run(name, candles, external_data=external).output.series[0].values

        for hour, value in ((0, 1.0), (8, 2.0)):
            await repository.create(
                ExternalDataPointModel(
                    source=source, symbol=None, timestamp=T0 + timedelta(hours=hour), value=value
                )
            )
        baseline = await current()
        assert baseline == [1.0, 2.0]

        await repository.create(
            ExternalDataPointModel(
                source=source, symbol=None, timestamp=T0 + timedelta(hours=24), value=999_999.0
            )
        )
        assert await current() == baseline
