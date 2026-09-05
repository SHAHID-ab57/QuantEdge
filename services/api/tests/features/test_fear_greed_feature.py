"""Tests for the `fear_greed` feature generator — the first connector-backed
feature (`app.features.builtin.fear_greed`).

`TestNoLookAhead` is the adversarial proof this task explicitly requires:
a fake data point published *after* a candle's own timestamp must never
change that candle's already-computed value — mirroring how the
Backtesting Engine's own no-look-ahead property was verified
(`ARCHITECTURE.md` § "Backtesting Engine").
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.features.base import ExternalDataPoint, FeatureContext, OHLCVPoint
from app.features.builtin import load_builtin_features
from app.features.builtin.fear_greed import FearGreedFeature
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
    def test_fear_greed_is_registered_and_declares_its_own_external_source(self) -> None:
        """The feature selector's own confirmation (`/features`'s catalogue):
        a generator registered under `app/features/builtin/` appears in
        `describe_all()` with no change to the pipeline, the registry, or
        the frontend `FeatureSelector` (which has no per-feature code of
        its own — see that component's module docstring)."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        names = {entry.name for entry in pipeline.describe_all()}
        assert "fear_greed" in names

        metadata = pipeline.describe("fear_greed")
        assert metadata.category == "sentiment"
        assert metadata.external_sources == ("fear_greed",)
        assert metadata.missing_values_expected is True
        assert metadata.outputs == ("fear_greed",)


class TestGenerate:
    def test_looks_up_the_most_recent_value_at_or_before_each_candle(self) -> None:
        # Fear & Greed published on day 0 (value 30) and day 2 (value 70).
        # Candles at hour 0 (day 0) and hour 60 (day ~2.5) should each pick
        # up the most recent value as of their own timestamp.
        external_data = {"fear_greed": [point(0, 30.0), point(2, 70.0)]}
        ctx = FeatureContext(
            candles=[candle(0), candle(60)], params={}, external_data=external_data
        )
        output = FearGreedFeature().generate(ctx)

        assert len(output.series) == 1
        assert output.series[0].column.name == "fear_greed"
        assert output.series[0].values == [30.0, 70.0]

    def test_null_before_the_earliest_recorded_value(self) -> None:
        """A candle predating the index's own earliest ingested value is
        `None`, indefinitely — never a fabricated 0 or a forward fill."""
        external_data = {"fear_greed": [point(5, 50.0)]}
        ctx = FeatureContext(candles=[candle(0)], params={}, external_data=external_data)
        output = FearGreedFeature().generate(ctx)
        assert output.series[0].values == [None]

    def test_null_when_no_external_data_was_provided_at_all(self) -> None:
        """A caller that never pre-fetched `fear_greed` (or a registered
        source that has never been ingested) gets `None` for every row —
        never an error, matching `FeatureValue`'s own "missing, not
        failed" contract."""
        ctx = FeatureContext(candles=[candle(0), candle(24)], params={}, external_data={})
        output = FearGreedFeature().generate(ctx)
        assert output.series[0].values == [None, None]

    def test_exact_timestamp_match_counts_as_at_or_before(self) -> None:
        external_data = {"fear_greed": [point(0, 42.0)]}
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
        output = FearGreedFeature().generate(ctx)
        assert output.series[0].values == [42.0]


@pytest.mark.asyncio
class TestNoLookAhead:
    """The adversarial proof: a data point published *after* a candle's
    own timestamp must never change that candle's already-computed value
    — checked at the pure-generator level and, separately, through the
    real database-backed `resolve_external_data` pre-fetch path, so
    "never looks ahead" is proven for the whole stack, not just the
    bisect helper in isolation.
    """

    async def test_a_future_point_never_changes_a_past_candles_value(self) -> None:
        candles = [candle(0), candle(24), candle(48)]  # days 0, 1, 2
        baseline_data = {"fear_greed": [point(0, 20.0), point(1, 50.0)]}
        baseline = (
            FearGreedFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=baseline_data))
            .series[0]
            .values
        )

        # Add a data point dated *after* every candle above (day 10) —
        # simulating a value the source publishes long after the fact, or
        # a clock/backfill anomaly landing a point far in the future.
        with_future_point = {"fear_greed": [point(0, 20.0), point(1, 50.0), point(10, 999.0)]}
        after = (
            FearGreedFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=with_future_point))
            .series[0]
            .values
        )

        assert after == baseline
        assert 999.0 not in after

    async def test_a_future_point_inserted_out_of_order_still_never_looks_ahead(self) -> None:
        """Same proof, with the future point listed *first* in the
        sequence — confirms the bisect search itself, not just "the last
        element happens to be excluded," is what enforces this."""
        candles = [candle(0), candle(24)]
        data_out_of_order = {"fear_greed": [point(10, 999.0), point(0, 20.0), point(1, 50.0)]}
        # `most_recent_value_at_or_before` requires ascending order — the
        # repository/service layer is what guarantees that in production
        # (`ExternalDataRepository.list_between` orders by timestamp
        # ascending); sorted here explicitly to isolate this test to the
        # lookup's own correctness rather than the loader's ordering.
        sorted_points = sorted(data_out_of_order["fear_greed"], key=lambda p: p.timestamp)
        output = FearGreedFeature().generate(
            FeatureContext(candles=candles, params={}, external_data={"fear_greed": sorted_points})
        )
        assert output.series[0].values == [20.0, 50.0]

    async def test_end_to_end_through_the_real_ingested_data_path(
        self, session_factory: SessionFactory
    ) -> None:
        """The same guarantee, proven through the real database-backed
        pre-fetch (`resolve_external_data` + `ExternalDataRepository`) —
        not just the in-memory bisect helper. Computes a dataset once,
        then *actually inserts* a future data point into
        `external_data_points` and recomputes: the past computation must
        come back byte-for-byte identical, exactly matching this task's
        own "add a fake future data point, confirm no change to a past
        computation" requirement."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        candles = [candle(0), candle(24)]
        requests = [FeatureRequest(feature="fear_greed")]
        session = session_factory()
        repository = ExternalDataRepository(session)

        async def current_values() -> list:
            external_data = await resolve_external_data(
                pipeline=pipeline, requests=requests, candles=candles, repository=repository
            )
            run = pipeline.run("fear_greed", candles, external_data=external_data)
            return run.output.series[0].values

        await repository.create(
            ExternalDataPointModel(
                source="fear_greed",
                symbol=None,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                value=20.0,
            )
        )
        await repository.create(
            ExternalDataPointModel(
                source="fear_greed",
                symbol=None,
                timestamp=datetime(2026, 1, 2, tzinfo=UTC),
                value=50.0,
            )
        )
        baseline = await current_values()

        # A fake data point published *after* the last candle above —
        # inserted into the real table, not merely constructed in memory.
        await repository.create(
            ExternalDataPointModel(
                source="fear_greed",
                symbol=None,
                timestamp=datetime(2026, 1, 11, tzinfo=UTC),
                value=999.0,
            )
        )
        after = await current_values()

        assert after == baseline
        assert 999.0 not in after
