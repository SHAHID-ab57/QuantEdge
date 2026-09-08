"""`app.services.candle_points.load_candle_points` — the shared candle
loader Indicators, Feature Engineering, the ML Dataset Builder, and every
Training Job's own dataset-rebuild step all go through.

The load-bearing regression case here (FIX-TRAINING-DATE-RANGE, found
while investigating M4-E3-T1): with no explicit `start`/`end`, this must
return the *most recent* candles for a market/timeframe, never the
*oldest* — the real bug that silently trained every model on this
platform's own earliest-ever candles, including the one driving live
paper trading. No test exercised this shared helper directly before this
file; every existing caller's own tests always passed an explicit range,
which is exactly why the bug was invisible.
"""

from decimal import Decimal

import pytest

from app.models import Candle, Exchange, Market
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.services.candle_points import load_candle_points
from app.services.market_query import InvalidRangeError
from tests.conftest import HOUR, SessionFactory, utc


@pytest.fixture
async def wide_market(session_factory: SessionFactory) -> None:
    """One market with 1,000 hourly candles, oldest to newest, distinct
    closing prices so "the 5 oldest" and "the 5 most recent" are
    trivially, unambiguously distinguishable."""
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol="ETHUSD",
            base_asset="ETH",
            quote_asset="USD",
            market_type="perpetual",
        )
        session.add(market)
        await session.commit()
        market_id = market.id
        for hour in range(1000):
            open_time = utc(hour)
            price = Decimal(1000 + hour)
            session.add(
                Candle(
                    market_id=market_id,
                    timeframe="1h",
                    open_time=open_time,
                    close_time=open_time + HOUR,
                    open=price,
                    high=price + 1,
                    low=price - 1,
                    close=price,
                    volume=Decimal(10),
                    quote_volume=None,
                    trade_count=None,
                    source="delta",
                )
            )
        await session.commit()


@pytest.mark.usefixtures("wide_market")
class TestNoExplicitRangeDefaultsToRecent:
    async def test_returns_the_most_recent_candles_not_the_oldest(
        self, session_factory: SessionFactory
    ) -> None:
        """The regression proof: hours 0-999 exist; with no start/end and
        limit=5, this must return hours 995-999 (the most recent), never
        hours 0-4 (the oldest) — the exact silent failure mode that had
        every training job on this platform training on a market's
        earliest-ever candles."""
        async with session_factory() as session:
            loaded = await load_candle_points(
                symbol="ETHUSD",
                timeframe="1h",
                market_repository=MarketRepository(session),
                candle_repository=CandleRepository(session),
                default_limit=5,
                max_limit=2000,
            )

        assert [point.open_time for point in loaded.points] == [utc(h) for h in range(995, 1000)]

    async def test_returned_points_are_still_in_ascending_order(
        self, session_factory: SessionFactory
    ) -> None:
        """Descending is only how the query itself fetches "the most
        recent N" efficiently — every consumer downstream (indicator
        warmup, feature/target computation) requires ascending
        chronological order, unchanged from before this fix."""
        async with session_factory() as session:
            loaded = await load_candle_points(
                symbol="ETHUSD",
                timeframe="1h",
                market_repository=MarketRepository(session),
                candle_repository=CandleRepository(session),
                default_limit=10,
                max_limit=2000,
            )

        open_times = [point.open_time for point in loaded.points]
        assert open_times == sorted(open_times)

    async def test_an_explicit_limit_still_returns_the_most_recent_that_many(
        self, session_factory: SessionFactory
    ) -> None:
        async with session_factory() as session:
            loaded = await load_candle_points(
                symbol="ETHUSD",
                timeframe="1h",
                market_repository=MarketRepository(session),
                candle_repository=CandleRepository(session),
                default_limit=5,
                max_limit=2000,
                limit=20,
            )

        assert [point.open_time for point in loaded.points] == [utc(h) for h in range(980, 1000)]


@pytest.mark.usefixtures("wide_market")
class TestExplicitRangeUnaffected:
    async def test_an_explicit_start_and_end_are_honored_oldest_first_within_it(
        self, session_factory: SessionFactory
    ) -> None:
        """Naming a specific range is untouched by this fix — a caller
        who asks for hours 10-14 still gets exactly hours 10-14, in
        ascending order, same as always."""
        async with session_factory() as session:
            loaded = await load_candle_points(
                symbol="ETHUSD",
                timeframe="1h",
                market_repository=MarketRepository(session),
                candle_repository=CandleRepository(session),
                default_limit=100,
                max_limit=2000,
                start=utc(10),
                end=utc(15),
            )

        assert [point.open_time for point in loaded.points] == [utc(h) for h in range(10, 15)]

    async def test_a_half_specified_range_is_still_rejected(
        self, session_factory: SessionFactory
    ) -> None:
        async with session_factory() as session:
            with pytest.raises(InvalidRangeError):
                await load_candle_points(
                    symbol="ETHUSD",
                    timeframe="1h",
                    market_repository=MarketRepository(session),
                    candle_repository=CandleRepository(session),
                    default_limit=100,
                    max_limit=2000,
                    start=utc(10),
                )
