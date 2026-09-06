"""Tests for the `fed_funds_rate` feature generator — the second
connector-backed feature (`app.features.builtin.fed_funds_rate`), after
`fear_greed`.

`TestNoLookAhead` mirrors `test_fear_greed_feature.py`'s own adversarial
proof exactly. `TestPublicationLagFixture` is the one genuinely new
requirement this connector's own investigation raised: FEDFUNDS's own
`date` (the calendar month it averages) is not the same as when that
value actually became knowable (`realtime_start`) — this class proves
the feature uses the latter, through the real connector's own mapping,
not a hand-picked timestamp construction.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.connectors.fred import FRED_SOURCE, FredClient, FredConnector
from app.features.base import ExternalDataPoint, FeatureContext, OHLCVPoint
from app.features.builtin import load_builtin_features
from app.features.builtin.fed_funds_rate import FedFundsRateFeature
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
    def test_fed_funds_rate_is_registered_and_declares_its_own_external_source(self) -> None:
        """The feature selector's own confirmation (`/features`'s catalogue):
        a generator registered under `app/features/builtin/` appears in
        `describe_all()` with no change to the pipeline, the registry, or
        the frontend `FeatureSelector` (which has no per-feature code of
        its own — see that component's module docstring)."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        names = {entry.name for entry in pipeline.describe_all()}
        assert "fed_funds_rate" in names

        metadata = pipeline.describe("fed_funds_rate")
        assert metadata.category == "macro"
        assert metadata.external_sources == (FRED_SOURCE,)
        assert metadata.missing_values_expected is True
        assert metadata.outputs == ("fed_funds_rate",)


class TestGenerate:
    def test_looks_up_the_most_recent_value_at_or_before_each_candle(self) -> None:
        external_data = {FRED_SOURCE: [point(0, 4.5), point(2, 4.25)]}
        ctx = FeatureContext(
            candles=[candle(0), candle(60)], params={}, external_data=external_data
        )
        output = FedFundsRateFeature().generate(ctx)

        assert len(output.series) == 1
        assert output.series[0].column.name == "fed_funds_rate"
        assert output.series[0].values == [4.5, 4.25]

    def test_null_before_the_earliest_recorded_value(self) -> None:
        external_data = {FRED_SOURCE: [point(5, 4.5)]}
        ctx = FeatureContext(candles=[candle(0)], params={}, external_data=external_data)
        output = FedFundsRateFeature().generate(ctx)
        assert output.series[0].values == [None]

    def test_null_when_no_external_data_was_provided_at_all(self) -> None:
        ctx = FeatureContext(candles=[candle(0), candle(24)], params={}, external_data={})
        output = FedFundsRateFeature().generate(ctx)
        assert output.series[0].values == [None, None]

    def test_exact_timestamp_match_counts_as_at_or_before(self) -> None:
        external_data = {FRED_SOURCE: [point(0, 4.33)]}
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
        output = FedFundsRateFeature().generate(ctx)
        assert output.series[0].values == [4.33]


@pytest.mark.asyncio
class TestNoLookAhead:
    """The adversarial proof this task explicitly requires: a data point
    published *after* a candle's own timestamp must never change that
    candle's already-computed value."""

    async def test_a_future_point_never_changes_a_past_candles_value(self) -> None:
        candles = [candle(0), candle(24), candle(48)]
        baseline_data = {FRED_SOURCE: [point(0, 4.5), point(1, 4.25)]}
        baseline = (
            FedFundsRateFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=baseline_data))
            .series[0]
            .values
        )

        with_future_point = {
            FRED_SOURCE: [point(0, 4.5), point(1, 4.25), point(10, 99.0)],
        }
        after = (
            FedFundsRateFeature()
            .generate(FeatureContext(candles=candles, params={}, external_data=with_future_point))
            .series[0]
            .values
        )

        assert after == baseline
        assert 99.0 not in after

    async def test_a_future_point_inserted_out_of_order_still_never_looks_ahead(self) -> None:
        candles = [candle(0), candle(24)]
        data_out_of_order = {FRED_SOURCE: [point(10, 99.0), point(0, 4.5), point(1, 4.25)]}
        sorted_points = sorted(data_out_of_order[FRED_SOURCE], key=lambda p: p.timestamp)
        output = FedFundsRateFeature().generate(
            FeatureContext(candles=candles, params={}, external_data={FRED_SOURCE: sorted_points})
        )
        assert output.series[0].values == [4.5, 4.25]

    async def test_end_to_end_through_the_real_ingested_data_path(
        self, session_factory: SessionFactory
    ) -> None:
        """The same guarantee, through the real database-backed pre-fetch
        (`resolve_external_data` + `ExternalDataRepository`)."""
        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        candles = [candle(0), candle(24)]
        requests = [FeatureRequest(feature="fed_funds_rate")]
        session = session_factory()
        repository = ExternalDataRepository(session)

        async def current_values() -> list:
            external_data = await resolve_external_data(
                pipeline=pipeline, requests=requests, candles=candles, repository=repository
            )
            run = pipeline.run("fed_funds_rate", candles, external_data=external_data)
            return run.output.series[0].values

        await repository.create(
            ExternalDataPointModel(
                source=FRED_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                value=4.5,
            )
        )
        await repository.create(
            ExternalDataPointModel(
                source=FRED_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 2, tzinfo=UTC),
                value=4.25,
            )
        )
        baseline = await current_values()

        await repository.create(
            ExternalDataPointModel(
                source=FRED_SOURCE,
                symbol=None,
                timestamp=datetime(2026, 1, 11, tzinfo=UTC),
                value=99.0,
            )
        )
        after = await current_values()

        assert after == baseline
        assert 99.0 not in after


@pytest.mark.asyncio
class TestPublicationLagFixture:
    """The requirement this connector's own investigation raised: FEDFUNDS
    dates a monthly average at the *first day of that month*, but the
    value isn't actually knowable until roughly a month later. This class
    proves the feature genuinely uses `realtime_start` (the real
    publication date), not `date` (the reference month) — through the
    real connector's own mapping and real ingestion, not a hand-picked
    timestamp.
    """

    async def test_a_candle_mid_reference_month_sees_no_value_yet(
        self, session_factory: SessionFactory
    ) -> None:
        """August's own average (`date: "2026-08-01"`) is not published
        until `realtime_start: "2026-09-01"` — a candle in the *middle*
        of August, after the reference date but before the real
        publication date, must not see it."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "observations": [
                        {
                            "realtime_start": "2026-09-01",
                            "realtime_end": "2026-09-01",
                            "date": "2026-08-01",
                            "value": "3.63",
                        },
                    ]
                },
            )

        client = FredClient(transport=httpx.MockTransport(handler), api_key="test-key")
        async with FredConnector(client=client) as connector:
            points = await connector.fetch(
                datetime(1954, 7, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC)
            )

        session = session_factory()
        repository = ExternalDataRepository(session)
        for raw_point in points:
            await repository.create(
                ExternalDataPointModel(
                    source=FRED_SOURCE,
                    symbol=None,
                    timestamp=raw_point.timestamp,
                    value=raw_point.value,
                    raw_payload=raw_point.raw_payload,
                )
            )

        load_builtin_features()
        pipeline = FeaturePipeline(default_registry)
        requests = [FeatureRequest(feature="fed_funds_rate")]

        mid_august = OHLCVPoint(
            open_time=datetime(2026, 8, 15, tzinfo=UTC),
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
        after_publication = OHLCVPoint(
            open_time=datetime(2026, 9, 2, tzinfo=UTC),
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )

        external_data = await resolve_external_data(
            pipeline=pipeline,
            requests=requests,
            candles=[mid_august, after_publication],
            repository=repository,
        )
        run = pipeline.run(
            "fed_funds_rate", [mid_august, after_publication], external_data=external_data
        )

        # Mid-August: the reference month has started, but the value is
        # not yet published — must be null, never a look-ahead value of
        # 3.63 that used the naive `date` field.
        assert run.output.series[0].values[0] is None
        # The instant after real publication: now knowable.
        assert run.output.series[0].values[1] == 3.63
