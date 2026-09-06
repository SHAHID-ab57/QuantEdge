"""Tests for the `eth_tvl` feature generator — the fourth connector-backed
generator (`app.connectors.defillama`), after `fear_greed`, `fed_funds_rate`,
and `eth_gas_price`.

`TestNoLookAhead` mirrors the other three features' own adversarial proof
exactly. `TestRevisionHandling` is the one genuinely new class this
source requires: `eth_tvl` is registered `revisable=True`
(`app.connectors.defillama`'s own module docstring has the full
investigation behind that decision) — an already-stored value can be
overwritten in place by a later ingestion run, and this feature's own
lookup must reflect whatever is *currently* stored, not whatever was
first ingested.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.connectors.defillama import DEFILLAMA_SOURCE
from app.features.base import ExternalDataPoint, FeatureContext, OHLCVPoint
from app.features.builtin import load_builtin_features
from app.features.builtin.defillama_eth_tvl import DefiLlamaEthTvlFeature
from app.features.dataset import FeatureRequest
from app.features.pipeline import FeaturePipeline
from app.features.registry import default_registry
from app.models.external_data import ExternalDataPoint as ExternalDataPointModel
from app.repositories.external_data import ExternalDataRepository
from app.services.external_data_context import resolve_external_data
from app.services.external_data_ingest import ingest_external_data
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
    def test_eth_tvl_is_registered_and_declares_its_own_external_source(self) -> None:
        """The feature selector's own confirmation (`/features`'s catalogue):
        a generator registered under `app/features/builtin/` appears in
        `describe_all()` with no change to the pipeline, the registry, or
        the frontend `FeatureSelector`."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        names = {entry.name for entry in pipeline.describe_all()}
        assert "eth_tvl" in names

        metadata = pipeline.describe("eth_tvl")
        assert metadata.category == "on-chain"
        assert metadata.external_sources == (DEFILLAMA_SOURCE,)
        assert metadata.missing_values_expected is True
        assert metadata.outputs == ("eth_tvl",)


class TestGenerate:
    def test_looks_up_the_most_recent_value_at_or_before_each_candle(self) -> None:
        external_data = {DEFILLAMA_SOURCE: [point(0, 40_000_000_000.0), point(2, 41_000_000_000.0)]}
        ctx = FeatureContext(
            candles=[candle(0), candle(60)], params={}, external_data=external_data
        )
        output = DefiLlamaEthTvlFeature().generate(ctx)

        assert len(output.series) == 1
        assert output.series[0].column.name == "eth_tvl"
        assert output.series[0].values == [40_000_000_000.0, 41_000_000_000.0]

    def test_null_before_the_earliest_recorded_value(self) -> None:
        external_data = {DEFILLAMA_SOURCE: [point(5, 40_000_000_000.0)]}
        ctx = FeatureContext(candles=[candle(0)], params={}, external_data=external_data)
        output = DefiLlamaEthTvlFeature().generate(ctx)
        assert output.series[0].values == [None]

    def test_null_when_no_external_data_was_provided_at_all(self) -> None:
        ctx = FeatureContext(candles=[candle(0), candle(24)], params={}, external_data={})
        output = DefiLlamaEthTvlFeature().generate(ctx)
        assert output.series[0].values == [None, None]

    def test_exact_timestamp_match_counts_as_at_or_before(self) -> None:
        external_data = {DEFILLAMA_SOURCE: [point(0, 40_000_000_000.0)]}
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
        output = DefiLlamaEthTvlFeature().generate(ctx)
        assert output.series[0].values == [40_000_000_000.0]


@pytest.mark.asyncio
class TestNoLookAhead:
    """The adversarial proof this task explicitly requires, run in full
    for `eth_tvl` too — identical shape to the other three features."""

    async def test_a_future_point_never_changes_a_past_candles_value(self) -> None:
        candles = [candle(0), candle(24), candle(48)]
        baseline_data = {DEFILLAMA_SOURCE: [point(0, 40_000_000_000.0), point(1, 41_000_000_000.0)]}
        baseline = (
            DefiLlamaEthTvlFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=baseline_data))
            .series[0]
            .values
        )

        with_future_point = {
            DEFILLAMA_SOURCE: [
                point(0, 40_000_000_000.0),
                point(1, 41_000_000_000.0),
                point(10, 999_000_000_000.0),
            ]
        }
        after = (
            DefiLlamaEthTvlFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=with_future_point))
            .series[0]
            .values
        )

        assert after == baseline
        assert 999_000_000_000.0 not in after

    async def test_a_future_point_inserted_out_of_order_still_never_looks_ahead(self) -> None:
        candles = [candle(0), candle(24)]
        data_out_of_order = {
            DEFILLAMA_SOURCE: [
                point(10, 999_000_000_000.0),
                point(0, 40_000_000_000.0),
                point(1, 41_000_000_000.0),
            ]
        }
        sorted_points = sorted(data_out_of_order[DEFILLAMA_SOURCE], key=lambda p: p.timestamp)
        output = DefiLlamaEthTvlFeature().generate(
            FeatureContext(
                candles=candles, params={}, external_data={DEFILLAMA_SOURCE: sorted_points}
            )
        )
        assert output.series[0].values == [40_000_000_000.0, 41_000_000_000.0]

    async def test_end_to_end_through_the_real_ingested_data_path(
        self, session_factory: SessionFactory
    ) -> None:
        """The same guarantee, through the real database-backed pre-fetch
        (`resolve_external_data` + `ExternalDataRepository`)."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        candles = [candle(0), candle(24)]
        requests = [FeatureRequest(feature="eth_tvl")]
        session = session_factory()
        repository = ExternalDataRepository(session)

        async def current_values() -> list:
            external_data = await resolve_external_data(
                pipeline=pipeline, requests=requests, candles=candles, repository=repository
            )
            run = pipeline.run("eth_tvl", candles, external_data=external_data)
            return run.output.series[0].values

        await repository.create(
            ExternalDataPointModel(
                source=DEFILLAMA_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                value=40_000_000_000.0,
            )
        )
        await repository.create(
            ExternalDataPointModel(
                source=DEFILLAMA_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 2, tzinfo=UTC),
                value=41_000_000_000.0,
            )
        )
        baseline = await current_values()

        await repository.create(
            ExternalDataPointModel(
                source=DEFILLAMA_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 11, tzinfo=UTC),
                value=999_000_000_000.0,
            )
        )
        after = await current_values()

        assert after == baseline
        assert 999_000_000_000.0 not in after


@pytest.mark.asyncio
class TestRevisionHandling:
    """The revision-handling decision this task's own investigation
    required (`ConnectorMetadata.revisable`, `app.connectors.defillama`'s
    own module docstring): a re-fetch reporting a *different* value for
    an already-stored date overwrites it in place, through the real
    ingestion path — not just the isolated `_persist_points` unit tests
    in `tests/services/test_external_data_ingest.py`, but through this
    feature's own lookup, proving a dataset built *after* a revision
    genuinely reflects it.
    """

    async def test_a_later_ingestion_run_that_revises_a_stored_value_changes_the_feature_output(
        self, session_factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from typing import ClassVar

        from app.connectors.base import ConnectorMetadata, RawDataPoint
        from app.connectors.registry import ConnectorRegistry
        from app.services import external_data_ingest as ingest_module

        class FakeRevisableConnector:
            metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
                source=DEFILLAMA_SOURCE, label="Fake", description="test double", revisable=True
            )
            points: ClassVar[tuple[RawDataPoint, ...]] = ()

            async def fetch(self, start: datetime, end: datetime) -> tuple[RawDataPoint, ...]:
                return FakeRevisableConnector.points

        registry = ConnectorRegistry()
        registry.register(FakeRevisableConnector)
        monkeypatch.setattr(ingest_module, "default_connector_registry", registry)
        monkeypatch.setattr(ingest_module, "load_builtin_connectors", lambda: None)

        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        candles = [candle(0)]
        requests = [FeatureRequest(feature="eth_tvl")]

        as_of = datetime(2026, 1, 1, tzinfo=UTC)

        async def current_value() -> object:
            session = session_factory()
            repository = ExternalDataRepository(session)
            external_data = await resolve_external_data(
                pipeline=pipeline, requests=requests, candles=candles, repository=repository
            )
            run = pipeline.run("eth_tvl", candles, external_data=external_data)
            return run.output.series[0].values[0]

        FakeRevisableConnector.points = (RawDataPoint(timestamp=as_of, value=40_000_000_000.0),)
        first_report = await ingest_external_data(
            source=DEFILLAMA_SOURCE, start=as_of, end=as_of, session=session_factory()
        )
        assert first_report.inserted == 1
        assert first_report.updated == 0
        assert await current_value() == 40_000_000_000.0

        # DefiLlama "revises" the same date's TVL on a later sync tick.
        FakeRevisableConnector.points = (RawDataPoint(timestamp=as_of, value=40_500_000_000.0),)
        second_report = await ingest_external_data(
            source=DEFILLAMA_SOURCE, start=as_of, end=as_of, session=session_factory()
        )
        assert second_report.inserted == 0
        assert second_report.updated == 1
        assert second_report.duplicates_skipped == 0
        assert await current_value() == 40_500_000_000.0

        # Re-fetching the *same* (already-revised) value a third time is
        # still just a duplicate skip, never a wasted rewrite.
        third_report = await ingest_external_data(
            source=DEFILLAMA_SOURCE, start=as_of, end=as_of, session=session_factory()
        )
        assert third_report.updated == 0
        assert third_report.duplicates_skipped == 1
        assert await current_value() == 40_500_000_000.0
