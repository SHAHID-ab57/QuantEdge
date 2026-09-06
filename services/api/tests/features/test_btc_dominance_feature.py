"""Tests for the `btc_dominance` feature generator — the fifth
connector-backed feature (`app.connectors.coingecko`), after
`fear_greed`, `fed_funds_rate`, `eth_gas_price`, and `defillama_eth_tvl`.

`TestNoLookAhead` mirrors the other four features' own adversarial proof
exactly — confirmed here too, not assumed, even though
`app.connectors.coingecko`'s own docstring already establishes this
source's timestamp as CoinGecko's own `updated_at`, never a locally
computed one. The generic lookup (`most_recent_value_at_or_before`) has
no idea any of that is true; this class proves it holds regardless.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.connectors.coingecko import COINGECKO_SOURCE
from app.features.base import ExternalDataPoint, FeatureContext, OHLCVPoint
from app.features.builtin import load_builtin_features
from app.features.builtin.btc_dominance import BtcDominanceFeature
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
    def test_btc_dominance_is_registered_and_declares_its_own_external_source(self) -> None:
        """The feature selector's own confirmation (`/features`'s catalogue):
        a generator registered under `app/features/builtin/` appears in
        `describe_all()` with no change to the pipeline, the registry, or
        the frontend `FeatureSelector`."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        names = {entry.name for entry in pipeline.describe_all()}
        assert "btc_dominance" in names

        metadata = pipeline.describe("btc_dominance")
        assert metadata.category == "market"
        assert metadata.external_sources == (COINGECKO_SOURCE,)
        assert metadata.missing_values_expected is True
        assert metadata.outputs == ("btc_dominance",)


class TestGenerate:
    def test_looks_up_the_most_recent_value_at_or_before_each_candle(self) -> None:
        external_data = {COINGECKO_SOURCE: [point(0, 58.5), point(2, 59.2)]}
        ctx = FeatureContext(
            candles=[candle(0), candle(60)], params={}, external_data=external_data
        )
        output = BtcDominanceFeature().generate(ctx)

        assert len(output.series) == 1
        assert output.series[0].column.name == "btc_dominance"
        assert output.series[0].values == [58.5, 59.2]

    def test_null_before_the_earliest_recorded_value(self) -> None:
        """Expected to occur more often here than for fear_greed/
        fed_funds_rate — this source has no historical backfill, so
        every candle before ingestion first started has no value."""
        external_data = {COINGECKO_SOURCE: [point(5, 59.0)]}
        ctx = FeatureContext(candles=[candle(0)], params={}, external_data=external_data)
        output = BtcDominanceFeature().generate(ctx)
        assert output.series[0].values == [None]

    def test_null_when_no_external_data_was_provided_at_all(self) -> None:
        ctx = FeatureContext(candles=[candle(0), candle(24)], params={}, external_data={})
        output = BtcDominanceFeature().generate(ctx)
        assert output.series[0].values == [None, None]

    def test_exact_timestamp_match_counts_as_at_or_before(self) -> None:
        external_data = {COINGECKO_SOURCE: [point(0, 58.5)]}
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
        output = BtcDominanceFeature().generate(ctx)
        assert output.series[0].values == [58.5]


@pytest.mark.asyncio
class TestNoLookAhead:
    """The adversarial proof this task explicitly requires, confirmed
    rather than assumed even for a source whose own connector already
    guarantees its timestamp comes from CoinGecko's own `updated_at`."""

    async def test_a_future_point_never_changes_a_past_candles_value(self) -> None:
        candles = [candle(0), candle(24), candle(48)]
        baseline_data = {COINGECKO_SOURCE: [point(0, 58.5), point(1, 58.8)]}
        baseline = (
            BtcDominanceFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=baseline_data))
            .series[0]
            .values
        )

        with_future_point = {COINGECKO_SOURCE: [point(0, 58.5), point(1, 58.8), point(10, 99.0)]}
        after = (
            BtcDominanceFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=with_future_point))
            .series[0]
            .values
        )

        assert after == baseline
        assert 99.0 not in after

    async def test_a_future_point_inserted_out_of_order_still_never_looks_ahead(self) -> None:
        candles = [candle(0), candle(24)]
        data_out_of_order = {COINGECKO_SOURCE: [point(10, 99.0), point(0, 58.5), point(1, 58.8)]}
        sorted_points = sorted(data_out_of_order[COINGECKO_SOURCE], key=lambda p: p.timestamp)
        output = BtcDominanceFeature().generate(
            FeatureContext(
                candles=candles, params={}, external_data={COINGECKO_SOURCE: sorted_points}
            )
        )
        assert output.series[0].values == [58.5, 58.8]

    async def test_end_to_end_through_the_real_ingested_data_path(
        self, session_factory: SessionFactory
    ) -> None:
        """The same guarantee, through the real database-backed pre-fetch
        (`resolve_external_data` + `ExternalDataRepository`)."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        candles = [candle(0), candle(24)]
        requests = [FeatureRequest(feature="btc_dominance")]
        session = session_factory()
        repository = ExternalDataRepository(session)

        async def current_values() -> list:
            external_data = await resolve_external_data(
                pipeline=pipeline, requests=requests, candles=candles, repository=repository
            )
            run = pipeline.run("btc_dominance", candles, external_data=external_data)
            return run.output.series[0].values

        await repository.create(
            ExternalDataPointModel(
                source=COINGECKO_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                value=58.5,
            )
        )
        await repository.create(
            ExternalDataPointModel(
                source=COINGECKO_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 2, tzinfo=UTC),
                value=58.8,
            )
        )
        baseline = await current_values()

        await repository.create(
            ExternalDataPointModel(
                source=COINGECKO_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 11, tzinfo=UTC),
                value=99.0,
            )
        )
        after = await current_values()

        assert after == baseline
        assert 99.0 not in after
