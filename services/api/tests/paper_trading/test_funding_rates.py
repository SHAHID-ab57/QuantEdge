"""Funding-rate history: the percent-to-fraction conversion, and ingestion
from Delta's public candle series.

**`TestPercentUnitIsEstablishedFromFirstPrinciples` is the dedicated test the
unit conversion rests on.** Delta publishes `funding_rate` in *percent*
(`0.01` = 0.01%). That was established by computing the rate from Delta's own
documented formula on real history and comparing it to the published figure
at 17 real funding times (research doc section 1.4). The 17 pairs are embedded
below; if the published value were a fraction the formula would be off by
about 0.53 percentage points on average, and read as a percent it is off by
about 0.001.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.integrations.delta import Product, ProductAsset, SeriesCandle
from app.models.exchange import Exchange
from app.models.funding_rate import FundingRate
from app.models.market import Market
from app.repositories.funding_rates import FundingRateRepository
from app.services.funding_rates import (
    FundingRateIngestService,
    funding_percent_to_fraction,
    funding_times_between,
)
from tests.conftest import SessionFactory

D = Decimal

#: `(funding time UTC, 8h TWAP of (mark - index) / index in PERCENT over the
#: 8h before it, the FUNDING:ETHUSD value Delta published at that time)`,
#: computed from real MARK:ETHUSD, .DEETHUSD and FUNDING:ETHUSD 5-minute
#: history for 2026-09-14 16:00 to 2026-09-20 00:00 UTC.
REAL_FUNDING_TIMES: list[tuple[str, float, float]] = [
    ("2026-09-14 16:00", -0.044876, 0.00298323),
    ("2026-09-15 00:00", -0.04698, 0.00185001),
    ("2026-09-15 08:00", -0.055495, -0.00668092),
    ("2026-09-15 16:00", -0.055503, -0.00493077),
    ("2026-09-16 00:00", -0.050901, -0.00057382),
    ("2026-09-16 08:00", -0.051655, -0.00249828),
    ("2026-09-16 16:00", -0.048978, 0.00281052),
    ("2026-09-17 00:00", -0.045402, 0.00348939),
    ("2026-09-17 08:00", -0.044337, 0.00545289),
    ("2026-09-17 16:00", -0.045545, 0.00579727),
    ("2026-09-18 00:00", -0.044708, 0.0043498),
    ("2026-09-18 08:00", -0.040198, 0.00927181),
    ("2026-09-18 16:00", -0.033834, 0.01),
    ("2026-09-19 00:00", -0.035357, 0.01),
    ("2026-09-19 08:00", -0.036387, 0.01),
    ("2026-09-19 16:00", -0.043648, 0.00275698),
    ("2026-09-20 00:00", -0.042618, 0.00758813),
]
INTEREST_RATE_PCT = 0.01
CLAMP_PCT = 0.05


def documented_funding_rate_pct(avg_premium_pct: float) -> float:
    """Delta's documented formula: `Premium + clamp(Interest - Premium, -0.05%, +0.05%)`."""
    return avg_premium_pct + max(-CLAMP_PCT, min(CLAMP_PCT, INTEREST_RATE_PCT - avg_premium_pct))


class TestPercentUnitIsEstablishedFromFirstPrinciples:
    def test_the_published_value_matches_the_documented_formula_read_as_percent(self) -> None:
        errors = [abs(documented_funding_rate_pct(p) - pub) for _, p, pub in REAL_FUNDING_TIMES]
        assert sum(errors) / len(errors) < 0.002
        assert max(errors) < 0.005

    def test_read_as_a_fraction_it_is_off_by_about_half_a_percentage_point(self) -> None:
        errors = [
            abs(documented_funding_rate_pct(p) - pub * 100) for _, p, pub in REAL_FUNDING_TIMES
        ]
        assert sum(errors) / len(errors) > 0.4  # the "fraction" reading is plainly wrong

    def test_three_funding_times_sit_exactly_on_the_interest_rate_floor(self) -> None:
        """The published `0.01` is the documented 0.01% interest-rate floor: 1% per
        8 hours if it were a fraction, which no perpetual charges."""
        assert [pub for _, _, pub in REAL_FUNDING_TIMES].count(0.01) == 3

    def test_the_conversion_gives_fractions_consistent_with_the_formula(self) -> None:
        for _, premium_pct, published in REAL_FUNDING_TIMES:
            fraction = funding_percent_to_fraction(D(str(published)))
            assert float(fraction) * 100 == pytest.approx(
                documented_funding_rate_pct(premium_pct), abs=0.005
            )

    def test_known_conversions(self) -> None:
        assert funding_percent_to_fraction(D("0.01")) == D("0.0001")
        assert funding_percent_to_fraction(D("-0.0067")) == D("-0.000067")
        assert funding_percent_to_fraction(D("0")) == D("0")
        # A real ticker value seen live: +0.0017% per 8h is a fraction of 0.0000167.
        assert funding_percent_to_fraction(D("0.001666603719307179")) == D("0.00001666603719307179")


class TestFundingTimes:
    def test_they_fall_on_multiples_of_the_interval_from_the_epoch(self) -> None:
        times = funding_times_between(
            datetime(2026, 9, 20, 1, 0, tzinfo=UTC), datetime(2026, 9, 21, 0, 0, tzinfo=UTC), 28800
        )
        assert times == [
            datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
            datetime(2026, 9, 20, 16, 0, tzinfo=UTC),
            datetime(2026, 9, 21, 0, 0, tzinfo=UTC),
        ]

    def test_the_bounds_are_inclusive_and_a_short_window_can_hold_none(self) -> None:
        exactly = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
        assert funding_times_between(exactly, exactly, 28800) == [exactly]
        assert (
            funding_times_between(
                exactly + timedelta(minutes=1), exactly + timedelta(hours=1), 28800
            )
            == []
        )
        assert funding_times_between(exactly, exactly, 0) == []


class FakeDeltaClient:
    """Serves Delta-shaped derived series (newest first, `volume: null`)."""

    def __init__(
        self,
        *,
        funding_pct: dict[datetime, str],
        index: dict[datetime, str],
        mark: dict[datetime, str],
        spot_index: str | None = ".DETESTUSD",
    ) -> None:
        self.funding_pct = funding_pct
        self.index = index
        self.mark = mark
        self.spot_index = spot_index
        self.series_requests: list[str] = []

    async def __aenter__(self) -> "FakeDeltaClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get_product(self, symbol: str) -> Product:
        return Product(
            id=1,
            symbol=symbol,
            contract_type="perpetual_futures",
            spot_index=ProductAsset(symbol=self.spot_index) if self.spot_index else None,
        )

    async def get_series(
        self, *, symbol: str, resolution: str, start: int, end: int
    ) -> list[SeriesCandle]:
        self.series_requests.append(symbol)
        if symbol.startswith("FUNDING:"):
            source = self.funding_pct
        elif symbol.startswith("MARK:"):
            source = self.mark
        else:
            assert symbol == self.spot_index
            source = self.index
        candles = [
            SeriesCandle(
                time=int(when.timestamp()),
                open=D(value),
                high=D(value),
                low=D(value),
                close=D(value),
                volume=None,
            )
            for when, value in source.items()
            if start <= int(when.timestamp()) < end
        ]
        return sorted(candles, key=lambda c: c.time, reverse=True)


async def seed_funding_market(
    session_factory: SessionFactory, symbol: str, *, interval: int | None = 28800
) -> Market:
    async with session_factory() as session:
        exchange = Exchange(name=f"X {symbol}", slug=f"x-{symbol.lower()}", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=symbol,
            base_asset=symbol[:3],
            quote_asset=symbol[3:],
            market_type="perpetual",
            funding_interval_seconds=interval,
        )
        session.add(market)
        await session.commit()
        await session.refresh(market)
        return market


T0 = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=8)
T2 = T0 + timedelta(hours=16)


@pytest.mark.asyncio
class TestFundingRateIngest:
    async def test_it_stores_the_rate_as_a_fraction_with_the_index_and_mark_at_the_funding_time(
        self, session_factory: SessionFactory
    ) -> None:
        market = await seed_funding_market(session_factory, "PTFRINGUSD")
        client = FakeDeltaClient(
            funding_pct={T0: "0.01", T1: "-0.0067", T2: "0.003171652"},
            index={T0: "2500.5", T1: "2510", T2: "2490.25"},
            mark={T0: "2501", T1: "2509", T2: "2491"},
        )
        async with session_factory() as session:
            created = await FundingRateIngestService(
                client,  # type: ignore[arg-type]
                FundingRateRepository(session),
            ).ingest(market, start=T0 - timedelta(minutes=5), end=T2 + timedelta(minutes=10))
        assert created == 3

        async with session_factory() as session:
            rows = (
                (await session.execute(select(FundingRate).order_by(FundingRate.funding_time)))
                .scalars()
                .all()
            )
        assert [float(r.funding_rate) for r in rows] == pytest.approx(
            [0.0001, -0.000067, 0.00003171652]
        )
        assert [float(r.index_price) for r in rows] == [2500.5, 2510.0, 2490.25]
        assert [float(r.mark_price) for r in rows] == [2501.0, 2509.0, 2491.0]
        # The FUNDING/MARK/index series were all asked for, the index by the
        # product's own `spot_index` symbol (not a guessed name).
        assert {"FUNDING:PTFRINGUSD", "MARK:PTFRINGUSD", ".DETESTUSD"} <= set(
            client.series_requests
        )

    async def test_re_ingesting_the_same_window_creates_nothing_new(
        self, session_factory: SessionFactory
    ) -> None:
        market = await seed_funding_market(session_factory, "PTFRIDEMUSD")
        client = FakeDeltaClient(funding_pct={T0: "0.01"}, index={T0: "2500"}, mark={T0: "2501"})
        for expected in (1, 0):
            async with session_factory() as session:
                created = await FundingRateIngestService(
                    client,  # type: ignore[arg-type]
                    FundingRateRepository(session),
                ).ingest(market, start=T0 - timedelta(hours=1), end=T0 + timedelta(hours=1))
            assert created == expected
        async with session_factory() as session:
            count = len((await session.execute(select(FundingRate))).scalars().all())
        assert count == 1

    async def test_a_funding_time_with_no_published_rate_or_index_is_skipped_for_later(
        self, session_factory: SessionFactory
    ) -> None:
        market = await seed_funding_market(session_factory, "PTFRSKIPUSD")
        client = FakeDeltaClient(
            funding_pct={T0: "0.01", T1: "0.02"},  # no funding candle at T2
            index={T0: "2500"},  # no index candle at T1
            mark={},
        )
        async with session_factory() as session:
            created = await FundingRateIngestService(
                client,  # type: ignore[arg-type]
                FundingRateRepository(session),
            ).ingest(market, start=T0 - timedelta(minutes=5), end=T2 + timedelta(minutes=10))
        assert created == 1  # only T0 has both

        async with session_factory() as session:
            [row] = (await session.execute(select(FundingRate))).scalars().all()
        assert row.mark_price is None  # mark is optional context, not required

    async def test_a_market_with_no_funding_interval_or_no_spot_index_ingests_nothing(
        self, session_factory: SessionFactory
    ) -> None:
        no_interval = await seed_funding_market(session_factory, "PTFRNOINTUSD", interval=None)
        no_index = await seed_funding_market(session_factory, "PTFRNOIDXUSD")
        async with session_factory() as session:
            repository = FundingRateRepository(session)
            assert (
                await FundingRateIngestService(
                    FakeDeltaClient(funding_pct={T0: "0.01"}, index={T0: "1"}, mark={}),  # type: ignore[arg-type]
                    repository,
                ).ingest(no_interval, start=T0, end=T2)
                == 0
            )
            assert (
                await FundingRateIngestService(
                    FakeDeltaClient(
                        funding_pct={T0: "0.01"}, index={T0: "1"}, mark={}, spot_index=None
                    ),  # type: ignore[arg-type]
                    repository,
                ).ingest(no_index, start=T0, end=T2)
                == 0
            )
