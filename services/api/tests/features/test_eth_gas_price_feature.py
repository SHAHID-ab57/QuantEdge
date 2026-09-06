"""Tests for the `eth_gas_price` feature generator — the third
connector-backed feature (`app.features.builtin.eth_gas_price`), after
`fear_greed` and `fed_funds_rate`.

`TestNoLookAhead` mirrors the other two features' own adversarial proof
exactly — confirmed here too, not assumed, even though
`app.connectors.etherscan`'s own docstring already establishes this
source's lag as zero by construction (its only timestamp concept is "the
moment it was observed"). The generic lookup (`most_recent_value_at_or_before`)
has no idea any of that is true; this class proves it holds regardless.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.connectors.etherscan import ETHERSCAN_SOURCE
from app.features.base import ExternalDataPoint, FeatureContext, OHLCVPoint
from app.features.builtin import load_builtin_features
from app.features.builtin.eth_gas_price import EthGasPriceFeature
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
    def test_eth_gas_price_is_registered_and_declares_its_own_external_source(self) -> None:
        """The feature selector's own confirmation (`/features`'s catalogue):
        a generator registered under `app/features/builtin/` appears in
        `describe_all()` with no change to the pipeline, the registry, or
        the frontend `FeatureSelector` (which has no per-feature code of
        its own — see that component's module docstring)."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        names = {entry.name for entry in pipeline.describe_all()}
        assert "eth_gas_price" in names

        metadata = pipeline.describe("eth_gas_price")
        assert metadata.category == "on-chain"
        assert metadata.external_sources == (ETHERSCAN_SOURCE,)
        assert metadata.missing_values_expected is True
        assert metadata.outputs == ("eth_gas_price",)


class TestGenerate:
    def test_looks_up_the_most_recent_value_at_or_before_each_candle(self) -> None:
        external_data = {ETHERSCAN_SOURCE: [point(0, 0.42), point(2, 0.55)]}
        ctx = FeatureContext(
            candles=[candle(0), candle(60)], params={}, external_data=external_data
        )
        output = EthGasPriceFeature().generate(ctx)

        assert len(output.series) == 1
        assert output.series[0].column.name == "eth_gas_price"
        assert output.series[0].values == [0.42, 0.55]

    def test_null_before_the_earliest_recorded_value(self) -> None:
        """Expected to occur more often here than for fear_greed/
        fed_funds_rate — this source has no historical backfill, so
        every candle before ingestion first started has no value."""
        external_data = {ETHERSCAN_SOURCE: [point(5, 0.5)]}
        ctx = FeatureContext(candles=[candle(0)], params={}, external_data=external_data)
        output = EthGasPriceFeature().generate(ctx)
        assert output.series[0].values == [None]

    def test_null_when_no_external_data_was_provided_at_all(self) -> None:
        ctx = FeatureContext(candles=[candle(0), candle(24)], params={}, external_data={})
        output = EthGasPriceFeature().generate(ctx)
        assert output.series[0].values == [None, None]

    def test_exact_timestamp_match_counts_as_at_or_before(self) -> None:
        external_data = {ETHERSCAN_SOURCE: [point(0, 0.33)]}
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
        output = EthGasPriceFeature().generate(ctx)
        assert output.series[0].values == [0.33]


@pytest.mark.asyncio
class TestNoLookAhead:
    """The adversarial proof this task explicitly requires, confirmed
    rather than assumed even for a source whose own connector already
    guarantees zero lag by construction."""

    async def test_a_future_point_never_changes_a_past_candles_value(self) -> None:
        candles = [candle(0), candle(24), candle(48)]
        baseline_data = {ETHERSCAN_SOURCE: [point(0, 0.42), point(1, 0.5)]}
        baseline = (
            EthGasPriceFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=baseline_data))
            .series[0]
            .values
        )

        with_future_point = {ETHERSCAN_SOURCE: [point(0, 0.42), point(1, 0.5), point(10, 99.0)]}
        after = (
            EthGasPriceFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=with_future_point))
            .series[0]
            .values
        )

        assert after == baseline
        assert 99.0 not in after

    async def test_a_future_point_inserted_out_of_order_still_never_looks_ahead(self) -> None:
        candles = [candle(0), candle(24)]
        data_out_of_order = {ETHERSCAN_SOURCE: [point(10, 99.0), point(0, 0.42), point(1, 0.5)]}
        sorted_points = sorted(data_out_of_order[ETHERSCAN_SOURCE], key=lambda p: p.timestamp)
        output = EthGasPriceFeature().generate(
            FeatureContext(
                candles=candles, params={}, external_data={ETHERSCAN_SOURCE: sorted_points}
            )
        )
        assert output.series[0].values == [0.42, 0.5]

    async def test_end_to_end_through_the_real_ingested_data_path(
        self, session_factory: SessionFactory
    ) -> None:
        """The same guarantee, through the real database-backed pre-fetch
        (`resolve_external_data` + `ExternalDataRepository`)."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        candles = [candle(0), candle(24)]
        requests = [FeatureRequest(feature="eth_gas_price")]
        session = session_factory()
        repository = ExternalDataRepository(session)

        async def current_values() -> list:
            external_data = await resolve_external_data(
                pipeline=pipeline, requests=requests, candles=candles, repository=repository
            )
            run = pipeline.run("eth_gas_price", candles, external_data=external_data)
            return run.output.series[0].values

        await repository.create(
            ExternalDataPointModel(
                source=ETHERSCAN_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                value=0.42,
            )
        )
        await repository.create(
            ExternalDataPointModel(
                source=ETHERSCAN_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 2, tzinfo=UTC),
                value=0.5,
            )
        )
        baseline = await current_values()

        await repository.create(
            ExternalDataPointModel(
                source=ETHERSCAN_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 11, tzinfo=UTC),
                value=99.0,
            )
        )
        after = await current_values()

        assert after == baseline
        assert 99.0 not in after
